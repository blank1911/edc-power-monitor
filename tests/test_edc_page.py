import pytest

from checks import edc_page
from checks.common import AVAILABLE, SOLD_OUT, STRUCTURE_BROKEN
from helpers import FIXTURES

ARGS = ("Bring Your Own RV (Dawn 4 Nights)", "Full Price with Power Add-On", "frontgatetickets.com")


def parse_fixture(name):
    return edc_page.parse((FIXTURES / name).read_text(encoding="utf-8"), *ARGS)


def test_current_page_dawn_power_sold_out():
    r = parse_fixture("edc_current_sold_out.html")
    assert r.status == SOLD_OUT
    assert "1,592.90" in r.detail


def test_dawn_power_buy_link_is_available():
    r = parse_fixture("edc_dawn_power_available.html")
    assert r.status == AVAILABLE
    assert r.items == ["https://edclasvegas.frontgatetickets.com/event/evli2snf7u1ewciq"]


def test_dawn_section_missing_is_structure_broken():
    assert parse_fixture("edc_dawn_section_missing.html").status == STRUCTURE_BROKEN


def test_dusk_change_does_not_affect_dawn():
    assert parse_fixture("edc_dusk_power_changed_only.html").status == SOLD_OUT


def test_dusk_on_sale_while_dawn_sold_out_does_not_alert():
    # The live page today: Dusk power has Buy Passes, Dawn power is SOLD OUT.
    html = (FIXTURES / "edc_current_sold_out.html").read_text(encoding="utf-8")
    assert "s2ruckl9ineqq7qq" in html
    assert edc_page.parse(html, *ARGS).status == SOLD_OUT


def test_power_row_missing_is_structure_broken():
    html = (FIXTURES / "edc_current_sold_out.html").read_text(encoding="utf-8")
    dawn_start = html.index("Bring Your Own RV (Dawn 4 Nights)")
    html = html[:dawn_start] + html[dawn_start:].replace("Full Price with Power Add-On", "Full Price Plus", 1)
    assert edc_page.parse(html, *ARGS).status == STRUCTURE_BROKEN


def test_sold_out_text_removed_counts_as_available():
    html = (FIXTURES / "edc_current_sold_out.html").read_text(encoding="utf-8")
    dawn_start = html.index("Bring Your Own RV (Dawn 4 Nights)")
    html = html[:dawn_start] + html[dawn_start:].replace("SOLD OUT", "Coming soon", 1)
    assert edc_page.parse(html, *ARGS).status == AVAILABLE


@pytest.mark.parametrize("sold", [True, False])
def test_table_layout_and_messy_whitespace(sold):
    status = "Sold&nbsp;Out" if sold else '<a href="https://edclasvegas.frontgatetickets.com/event/evli2snf7u1ewciq">Buy Passes</a>'
    html = f"""<html><body>
    <h3>Bring   Your Own RV
       (Dawn 4 Nights)</h3>
    <table>
      <tr><td>Deposit</td><td>$30</td><td><a href="https://edclasvegas.frontgatetickets.com/x">Buy Passes</a></td></tr>
      <tr><td>FULL PRICE with <strong>Power Add&#8209;On</strong></td><td>$1,592.90</td><td>{status}</td></tr>
    </table>
    <h3>Bring Your Own RV with Required Power Add-On (Dusk Till Dawn 11 Nights)</h3>
    <table><tr><td>Full Price with Power Add-On</td><td>$4,000</td><td><a href="https://edclasvegas.frontgatetickets.com/y">Buy Passes</a></td></tr></table>
    </body></html>"""
    assert edc_page.parse(html, *ARGS).status == (SOLD_OUT if sold else AVAILABLE)


def test_eleven_night_power_row_is_not_dawn():
    # Remove the Dawn power row; the 11 night section's power row must not be picked up instead.
    html = (FIXTURES / "edc_dawn_section_missing.html").read_text(encoding="utf-8")
    assert "Dusk Till Dawn 11 Nights" in html
    assert edc_page.parse(html, *ARGS).status == STRUCTURE_BROKEN

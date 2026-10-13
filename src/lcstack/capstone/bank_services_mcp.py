"""Kestrel Ridge Bank's branch-and-rates MCP server (stdio), owned by a different team than the support desk.

Read-only and fictional. The capstone's knowledge agent reaches it through langchain-mcp-adapters.
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("kestrel-bank-services", log_level="WARNING")
BRANCHES = {"harbourside": "Harbourside branch, 12 Quay Street, open 9:00-17:00 Mon-Fri, step-free access",
            "millbrook": "Millbrook branch, 3 Market Row, open 9:30-16:30 Mon-Sat"}  # fmt: skip
RATES = {"EUR": 0.912, "GBP": 0.781, "CAD": 1.366, "JPY": 148.2}


@server.tool()
def find_branch(city: str) -> str:
    """Nearest Kestrel branch and its opening hours for a town or city."""
    return BRANCHES.get(city.lower(), f"No Kestrel branch in {city}; the nearest options are Harbourside and Millbrook.")


@server.tool()
def fx_rate(currency: str) -> str:
    """Kestrel's indicative rate for 1 USD in another currency."""
    r = RATES.get(currency.upper())
    return f"1 USD = {r} {currency.upper()} (indicative, before the 2 percent card fee)" if r else f"No rate published for {currency}."


if __name__ == "__main__":
    server.run(transport="stdio")

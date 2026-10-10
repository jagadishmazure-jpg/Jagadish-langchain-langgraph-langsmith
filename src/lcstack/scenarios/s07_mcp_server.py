"""A tiny MCP server (stdio) owned by Wrenfield's store-systems team: read-only inventory and loyalty lookups.

Run by scenario 07 and by the capstone through langchain-mcp-adapters. Data is fictional and fixed.
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("wrenfield-inventory")
STOCK = {("SKU-OATS-1KG", "Riverside"): 14, ("SKU-OATS-1KG", "Harbour"): 0}
POINTS = {"C-118": 2310}


@server.tool()
def store_inventory(sku: str, store: str) -> str:
    """Units of a SKU on the shelf at one store."""
    n = STOCK.get((sku, store))
    return f"{sku} at {store}: unknown SKU or store." if n is None else f"{sku} at {store}: {n} units on the shelf."


@server.tool()
def loyalty_points(customer_id: str) -> str:
    """Loyalty points balance for a customer."""
    return f"Customer {customer_id} has {POINTS.get(customer_id, 0)} points."


if __name__ == "__main__":
    server.run(transport="stdio")

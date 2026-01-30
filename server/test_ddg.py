
try:
    from agno.tools.duckduckgo import DuckDuckGo
    print("DuckDuckGo loaded successfully")
    tool = DuckDuckGo(fixed_max_results=3)
    print(f"Tool created: {tool}")
    print(f"Tool name: {tool.name}")
except Exception as e:
    print(f"Error: {e}")

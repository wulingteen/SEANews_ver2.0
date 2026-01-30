
try:
    from agno.tools.duckduckgo import DuckDuckGo
    print("DuckDuckGo found")
except ImportError:
    print("DuckDuckGo NOT found")

try:
    from agno.tools.google_search import GoogleSearch
    print("GoogleSearch found")
except ImportError:
    print("GoogleSearch NOT found")

try:
    from agno.tools.googlesearch import GoogleSearch
    print("GoogleSearch (alt) found")
except ImportError:
    print("GoogleSearch (alt) NOT found")

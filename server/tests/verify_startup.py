
import sys
import os

# Add server to path
sys.path.append(os.path.join(os.getcwd(), 'server'))

try:
    print("Attempting to import agno_api...")
    from agno_api import app
    print("Successfully imported agno_api.app")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Startup failed: {e}")
    sys.exit(1)

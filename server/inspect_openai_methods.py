
import inspect
from agno.tools.openai import OpenAITools

print("Methods in OpenAITools:")
for name, obj in inspect.getmembers(OpenAITools):
    if inspect.isfunction(obj) or inspect.ismethod(obj):
        print(name)

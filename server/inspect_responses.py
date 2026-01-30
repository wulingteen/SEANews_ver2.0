import inspect
from agno.models.openai.responses import OpenAIResponses

print("Config for OpenAIResponses:")
sig = inspect.signature(OpenAIResponses.__init__)
for name, param in sig.parameters.items():
    print(f"  {name}: {param.annotation} = {param.default}")

print("\nMethod 'invoke' signature:")
if hasattr(OpenAIResponses, 'invoke'):
    sig_invoke = inspect.signature(OpenAIResponses.invoke)
    for name, param in sig_invoke.parameters.items():
        print(f"  {name}: {param.annotation} = {param.default}")
else:
    print("No 'invoke' method found.")

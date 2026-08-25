"""Test rapide de la cle Ollama Cloud."""
import os
os.environ["OLLAMA_API_KEY"] = "673e8e370c294a79936ad95c0feb8ccb.8uAktjvT_pvcaENqnmg6PsNF"

import ollama

client = ollama.Client(host="https://ollama.com")
models = client.list()
model_list = models.get("models", [])
print(f"Modeles accessibles : {len(model_list)}")
for m in model_list[:5]:
    name = m.get("model", "?")
    print(f"  - {name}")
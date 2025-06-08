import ollama

def ask_model(prompt: str) -> str:
    client = ollama.Client()
    model = "llama3.2"
    response = client.generate(model=model, prompt=prompt)
    return response.response

# #demo 
# prompt = "What is the capital of France?"
# result = ask_model(prompt)
# print(f"Model: llama3.2")
# print("response:")
# print(result)
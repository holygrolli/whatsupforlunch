import openai, sys
from datetime import datetime

# list models
models = openai.Model.list()

# print the first model's id
print(models.data[0].id)

fp = open(sys.argv[1], "r")
prompt = fp.read()
fp.close()

fcsv = open(sys.argv[2], "r")
input = fcsv.read()
fcsv.close()

# create a chat completion
chat_completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
    {"role": "system", "content": prompt},
    {"role": "user", "content": "The input is:\n" + input}])

print(chat_completion.usage)
# print the chat completion
print(chat_completion.choices[0].message.content)
out = open ("final.json", "w")
out.write(chat_completion.choices[0].message.content)
out.close()
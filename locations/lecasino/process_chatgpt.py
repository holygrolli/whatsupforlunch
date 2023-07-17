import openai, sys

# list models
models = openai.Model.list()

# print the first model's id
print(models.data[0].id)

fp = open(sys.argv[1], "r")
prompt = fp.read()
fp.close()

fcsv = open(sys.argv[2], "r")
csv = fcsv.read()
fcsv.close()
ftxt = open("output.txt", "r")
txt = ftxt.read()
ftxt.close()

# create a chat completion
chat_completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
    {"role": "system", "content": prompt},
    {"role": "user", "content": "The current week is defined as follows:\n" + txt + "The CSV data is:\n" + csv}])

print(chat_completion.usage)
# print the chat completion
print(chat_completion.choices[0].message.content)
out = open ("final.json", "w")
out.write(chat_completion.choices[0].message.content)
out.close()
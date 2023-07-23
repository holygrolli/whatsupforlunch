import openai, sys
from datetime import datetime, timedelta

# list models
models = openai.Model.list()

# print the first model's id
print(models.data[0].id)

fp = open(sys.argv[1], "r")
prompt = fp.read()
fp.close()

fInput = open(sys.argv[2], "r")
inputString = fInput.read()
fInput.close()

print("Using the prompt: " + prompt)
today = datetime.today()
weekStart = today - timedelta(days=today.weekday())
print(weekStart.strftime('%Y-%m-%d'))
# create a chat completion
chat_completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
    {"role": "system", "content": prompt},
    {"role": "user", "content": "assume today is " + weekStart.strftime('%Y-%m-%d') + " and the input is:\n" + inputString}])

print(chat_completion.usage)
# print the chat completion
print(chat_completion.choices[0].message.content)
out = open ("final.json", "w")
out.write(chat_completion.choices[0].message.content)
out.close()
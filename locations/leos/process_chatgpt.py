from datetime import datetime, timedelta
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat

today = datetime.today()
#print(today.strftime('%G-W%V'))

import base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Path to your image
image_path = sys.argv[2]

# Determine the mime type based on the file extension
if image_path.endswith('.png'):
        mime_type = 'png'
else:
        mime_type = 'jpeg'


# Getting the base64 string
base64_image = encode_image(image_path)

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(systemPromptFile=sys.argv[1], 
                userMessage="Assume this week is " + today.strftime('%G-W%V') + " then extract the JSON containing the meal offers from the following image!")

meal_chat.processImageAndWriteToFile(userImage=f"data:image/{mime_type};base64,{base64_image}")
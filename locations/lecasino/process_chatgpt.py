from datetime import datetime
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat

import base64
def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

# Path to your image
image_path = "image.png"

# Getting the base64 string
base64_image = encode_image(image_path)

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(systemPromptFile=sys.argv[1], 
                userMessage="Extract the JSON containing the meal offers from the following image!")

meal_chat.processImageAndWriteToFile(userImage=f"data:image/png;base64,{base64_image}")
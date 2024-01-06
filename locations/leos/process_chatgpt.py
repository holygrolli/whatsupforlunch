import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat
from config import config

# Path to your image
image_path = sys.argv[1]

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(
                userImageFile=image_path,
                **config)

meal_chat.processImageAndWriteToFile()
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat
from prompt_config import prompt_config
from config import config

# Path to your image
image_path = sys.argv[1]

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(
                userImageFile=image_path,
                **config,
                **prompt_config)

meal_chat.processImageAndWriteToFile()
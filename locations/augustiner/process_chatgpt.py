import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat
from config import config, prompt_overrides

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(
              **config,
              promptOverrides=prompt_overrides)

meal_chat.processAndWriteToFile()

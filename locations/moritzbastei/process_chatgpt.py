import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat
from prompt_config import prompt_config
from config import config

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat( 
                **config,
                **prompt_config)

meal_chat.processAndWriteToFile()

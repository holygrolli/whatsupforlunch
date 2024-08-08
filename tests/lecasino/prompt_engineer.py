import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/.shared')
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/' + os.path.basename(os.path.dirname(inspect.getfile(inspect.currentframe()))))
from DefaultMealChat import DefaultMealChat
from testconfig import testconfig

prompt_overrides = {
    "addCurrentDate": False,
    "systemPrompt": """You are an expert in prompt engineering. You will receive an image and a human crafted request to parse the image as a table. Based on your analyzis of the image answer with an optimized prompt to extract all meals and prices of the week menu from the image. Also include in your resulting prompt any required steps to understand the table layout if you think it is necessary."""
}
config = {
    "userImageFile": "image.png",
    "userMessage": """Print the menu of the week (meals and prices), each calendar date separate based on the following image""",
}
# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(
                config,
                **testconfig,
                promptOverrides=prompt_overrides)

meal_chat.processImageAndWriteToFile()
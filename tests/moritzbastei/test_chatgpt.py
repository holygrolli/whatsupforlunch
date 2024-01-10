import unittest
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/.shared')
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/' + os.path.basename(os.path.dirname(inspect.getfile(inspect.currentframe()))))
from DefaultMealChat import DefaultMealChat
from config import config, prompt_overrides
from testconfig import testconfig

class TestMoritzbastei(unittest.TestCase):
    def test_process_chatgpt(self):
        # Create an instance of DefaultMealChat
        meal_chat = DefaultMealChat(
                        **config,
                        **testconfig,
                        promptOverrides=prompt_overrides)

        meal_chat.processAndWriteToFile()
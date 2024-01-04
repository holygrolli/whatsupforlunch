import unittest
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/.shared')
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/' + os.path.basename(os.path.dirname(inspect.getfile(inspect.currentframe()))))
from DefaultMealChat import DefaultMealChat
from prompt_config import prompt_config
from config import config
from testconfig import testconfig

class TestMoritzbastei(unittest.TestCase):
    def test_process_chatgpt(self):
        # Create an instance of DefaultMealChat
        meal_chat = DefaultMealChat(
                        **config,
                        **testconfig,
                        **prompt_config)

        meal_chat.processAndWriteToFile()
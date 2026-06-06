import unittest
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/.shared')
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../../locations/' + os.path.basename(os.path.dirname(inspect.getfile(inspect.currentframe()))))
from DefaultMealChat import DefaultMealChat
from config import config, prompt_overrides
from testconfig import testconfig

class TestRatskeller(unittest.TestCase):
    def test_process_chatgpt(self):
        test_cases = [
            {"prompt_override": {"model_provider": "openai", "visionModel": "azure/gpt-4.1-nano@francecentral"}},
            {"prompt_override": {"model_provider": "google", "visionModel": "vertex/gemini-2.5-flash-lite@europe-central2"}},
        ]

        for case in test_cases:
            with self.subTest(case=case):
                # Create an instance of DefaultMealChat
                meal_chat = DefaultMealChat(
                                **config,
                                **testconfig,
                                promptOverrides={**prompt_overrides, **case["prompt_override"]}
                            )

                meal_chat.processImageAndWriteToFile()
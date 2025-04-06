config = {
    "userImageFile": "image.jpg",
    "userMessage": """Extract the JSON containing the meal offers from the following image of a week menu in table layout.
    
    Also keep following in mind:
    - Clean up each meal name and remove all line breaks and special characters and add commas and "und" where necessary.
    - All meals have the same price stated inside the image.
    - This menu has no week offers
    
    These points are most important before you finally create the JSON and shall be revised:
    - did you leave out the correct dates and are they actually empty. you cannot add a meal to a date which is a holiday but do not forget to add all meals to the date
    - did you add all dates to the JSON
    
    Explain if you leave out a day, but not for Saturday and Sunday!
    """,
    "max_tokens": 2000
}
prompt_overrides = {
    "addCurrentDate": True,
    "model_provider": "google",
    "visionModel": "gemini-2.0-flash"
}
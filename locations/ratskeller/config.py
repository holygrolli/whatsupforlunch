config = {
    "userImageFile": "image.png",
    "userMessage": """Extract the JSON containing the meal offers from the following image of a week menu in table layout.
    
    Also keep following in mind:
    - Each day is on a separate row
    - If you cannot find a price for a meal in the cell, leave the price empty.
    - This menu has no week offers
    
    These points are most important before you finally create the JSON and shall be revised:
    - did you leave out the correct dates and are they actually empty. you cannot add a meal to a date which is a holiday but do not forget to add all meals to the date
    - did you add all dates to the JSON
    
    Explain if you leave out a day, but not for Saturday and Sunday!
    """
}
prompt_overrides = {
    "addCurrentDate": False
}
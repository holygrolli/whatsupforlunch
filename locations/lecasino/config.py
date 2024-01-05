config = {
    "userImageFile": "image.png",
    "userMessage": """Extract the JSON containing the meal offers from the following image of a week menu in table layout. Consider these steps:
    1. Detect the week period which is defined in the headline by a start and end date, always seven days, starting on Monday as first day of the week, Sunday the last.
    2. Extract table data from the image below the headline. Try to make sure empty cells are correctly aligned!
    3. In the header row expect the first column to be meal categories, following 5 columns representing the weekdays Monday (the first date of the week) to Friday.
    4. Start processing the days. Start left from column Monday. Read the next 3 rows of that column and try to get a meal from that cell. Skip the following rows as they contain only side dishes. If you find an empty cell or note There might be no meal for that day during public holidays. When you do not identify any meal on a day just skip this date. Apply this step to the next columns until Friday.
    
    If you cannot find a price for a meal in the cell, leave the price empty. This menu has no week offers. Explain if you leave out a day, but not for Saturday and Sunday! Before you finally create the JSON revise if you left out the correct dates!"""
}
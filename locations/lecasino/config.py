config = {
    "userImageFile": "image.png",
    "userMessage": """You will receive an image with German text. Identify and index the tabular data within the image, which is structured with column headers representing days of the week (Monday to Friday) and row headers denoting the type of dish. Extract the text under each day’s column, and pair each meal item with its corresponding price. Take special care of identifying the columns as some days might start with empty cells. Use context clues to decide if this day is a public holiday and should not have any meal. When you find 'Tagesangebot' include it as a meal without a price. Include all 3 main dishes but ignore the sides. The menu does not include any week offer. Compile the extracted information in JSON.""",
}
prompt_overrides = {
    "addCurrentDate": True
}
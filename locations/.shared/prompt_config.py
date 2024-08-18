prompt_config = {
  "systemPrompt": """Your task is to process a meal menu which is provided to you. You answer will always contain a valid JSON object and a short description of the calendar period of the meal menu. Depending on the meal menu you may find meals grouped by weekday (we call it day offer). Add these days as keys formatted as `YYYY-MM-dd` to the JSON each having a list of meal objects. It is also possible that you will find daily meals which are valid throughout the week (we call it week offer). Add them to the JSON response object under an ISO 8601 week date key like "2023-W03" but with the actual calendar week of the restaurant's menu. This key also contains a list of meal objects. A meal object is built by a key `desc` with the meal's description and `price` with the meals price in number format with two decimal places. There might be both day offers and week offers or only one of each.
  
  This is an example of the expected JSON object:
  {MC_JSON_SCHEMA}
  
  When doing the processing consider these steps:
  1. Identify the dates the menu is valid for. If there are no dates in the input use the date of today. Always use the first calendar date of the detected period beginning which is Monday. Review that you map each weekday from Monday to Friday to a valid calendar date and that it is included in the JSON but only if you decide there is a day offer! 
  2. Identify if there are weekdays Monday through Friday and respective day offers. Do not get confused by empty days. There might be no day offer on that day due to public holidays. For this day just report back an empty array. It is also possible there are no day offers at all then there must be week offers! 
  3. Identify if there are week offers. If you find repeating meals for all days then use them as week offers!

  Remember to always include a valid JSON object containing at least either 5 keys containing day offers or one week key with week offers. If you leave out some days between Monday and Friday add an explaination at the end.
  """,
  "jsonSchema": """
  {
    "2023-10-30":[
      {
         "desc":"Schweineroulade, Rotkohl & Klöße",
         "price": 6.60
      },
      {
         "desc":"Seelachsfilet mit Tomatensoße und Kartoffelstampf",
         "price": 7.90
      }
   ],
   "2023-10-31":[],
   "2023-W44": [
      {
        "desc": "Spaghetti mit getrockneten Tomaten, Hirtenkäse & Rucola",
        "price": 4.90
      }
    ]
  }""",
  "addCurrentDate": True,
  "addCurrentWeekdays": True,
  "visionModel": "gpt-4o"
}
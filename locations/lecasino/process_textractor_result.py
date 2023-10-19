import os, sys
from textractor.entities.document import Document
from textractor.visualizers.entitylist import EntityList
from textractor.data.constants import TextractFeatures, Direction, DirectionalFinderType

document = Document.open(sys.argv[1])
print(document)
table = EntityList(document.tables[0])
print(table[0].to_csv())
csv = table[0].to_csv().split("\n")
f = open("table.csv", "w")
for i in range(1,5):
  f.write(csv[i] + "\n")
f.close()
f = open("output.txt", "w")
# first line with "Mittagsangebot"
print(document.lines[0])
f.write(document.lines[0].text+"\n")
f.close()
#document.tables[0].to_csv()
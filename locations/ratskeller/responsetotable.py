import os, sys
from textractor.entities.document import Document
from textractor.visualizers.entitylist import EntityList
from textractor.data.constants import TextractFeatures, Direction, DirectionalFinderType

document = Document.open(sys.argv[1])
print(document)
table = EntityList(document.tables[0])
print(table[0].to_csv())
f = open("table.csv", "w")
f.write(table[0].to_csv().split("\n",1)[1])
f.close()
#document.tables[0].to_csv()
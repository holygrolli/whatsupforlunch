import os, sys
from textractor.entities.document import Document
from textractor.visualizers.entitylist import EntityList
from textractor.data.constants import TextractFeatures, Direction, DirectionalFinderType

document = Document.open(sys.argv[1])
print(*document.lines, sep = "\n")
f = open("output.txt", "w")
for line in document.lines:
    print(line)
    f.write(line.text+"\n")
f.close()
#document.tables[0].to_csv()
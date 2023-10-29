import io, os, sys
import pandas as pd
from textractor.entities.document import Document
from textractor.visualizers.entitylist import EntityList
from textractor.data.constants import TextractFeatures, Direction, DirectionalFinderType

document = Document.open(sys.argv[1])
print(document)
table = EntityList(document.tables[0])
csv = table[0].to_csv()
print(csv)
# read csv string and transpose

# Read csv string and transpose
df = pd.read_csv(io.StringIO(csv), usecols=[1,2,3,4,5,6], skiprows=[5,6])
print(df)
df = df.transpose()

# Write transposed data to csv file
df.to_csv('table.csv', header=False, index=False)

# Write first line with "Mittagsangebot" to output.txt
with open('output.txt', 'w') as f:
    f.write(document.lines[0].text + '\n')
f.close()
#document.tables[0].to_csv()
import re
from lxml.html import parse; 
from sys import stdin;
from sys import exit as sys_exit;

date = parse(stdin).xpath('string(//meta[@property=\"article:modified_time\"]/@content)')
if re.match(r'\d{4}', date):
  print(date)
else:
  sys_exit(1)
import re
stdout = "1HSEb8PZRUE7Z1Tvd3ZtT0g [#b0b2b8 0B/0B(0%) CN:1 SD:0 DL:0B] "
match = re.search(r'\[.*? (\w+)/(\w+)\((.*?)\).*? DL:(.*?)]', stdout)
if match: print(match.groups())

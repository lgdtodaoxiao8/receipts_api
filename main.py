path = 'receipt.txt'

lines = []
with open(path, 'r') as f:
    lines = f.readlines()

for line in lines:
    print(line.strip()) 

print(f'Всего строк: {len(lines)}')

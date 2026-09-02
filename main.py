path = 'receipt.txt'

counter = 0
with open(path, encoding='utf-8') as f:
    for line in f:
        print(line.strip())
        counter += 1


print(f'Всего строк: {counter}')

path = 'receipt.txt'

lines_counter = 0

calculated_sum = 0
with open(path, encoding='utf-8') as f:
    for line in f:
        parts = line.strip().split()
        name = ' '.join(parts[:-1]) 
        price = int(parts[-1])
        if name == 'Итого':
            total = price
        else:
            calculated_sum += price
            print(f'{name} -> {price}')
            lines_counter += 1

discrepancy = calculated_sum - total

print(f'Всего строк: {lines_counter}')
print(f'Итого по чеку: {total}')
print(f'Итого по сумме: {calculated_sum}')
print(f'Расхождение относительно чека: {'+' if discrepancy > 0 else ''}{discrepancy}')

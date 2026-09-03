path = 'receipt.txt'

lines_counter = 0

calculated_sum = 0
total_formal = None

try:
    with open(path, encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()

            try:
                name = ' '.join(parts[:-1]) 
                price = int(parts[-1])
            except IndexError:
                print('Строка пустая')
                continue
            except ValueError:
                print(f'Цена в строке {' '.join(parts)} неверная')
                continue
            if name == 'Итого':
                total_formal = price
            else:
                calculated_sum += price
                print(f'{name} -> {price}')
                lines_counter += 1


    print(f'Всего позиций: {lines_counter}')
    print(f'Итого по сумме: {calculated_sum}')

    if total_formal is None:
        print('В чеке отсутствует итог.')
    else:
        discrepancy = calculated_sum - total_formal
        
        print(f'Итого по чеку: {total_formal}')
        if discrepancy == 0:
            print('Расхождения относительно чека нет')
        else:
            print(f'Расхождение относительно чека: {'+' if discrepancy > 0 else ''}{discrepancy}')
except FileNotFoundError:
    print('Файл не найден')


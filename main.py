path = 'receipt.txt'


def parse_line(line: str) -> tuple[str, int] | None:
    parts = line.strip().split()

    try:
        price = int(parts[-1])
        name = ' '.join(parts[:-1])
    except IndexError:
        print('Строка пустая')
        return None
    except ValueError:
        print(f'Цена в строке {' '.join(parts)} неверная')
        return None
    else:
        return name, price


def read_receipt(path: str) -> tuple[list[tuple[str, int]], int | None]:
    
    with open(path, encoding='utf-8') as f:
        pairs = []
        total = None
        for line in f:
            pair = parse_line(line)
            if pair is not None:
                if pair[0] == 'Итого':
                    total = pair[1]
                else:
                    pairs.append(pair)

    return pairs, total
        


def print_report(items: list[tuple[str, int]], total: int | None) -> None:
    calculated_total = 0

    for name, price in items:
        calculated_total += price

        print(f'{name} -> {price}')

    print(f'Всего строк: {len(items)}')

    print(f'Итого по сумме: {calculated_total}')

    if total is None:
        print('Итого отсутствует в чеке')
    else:
        print(f'Итого из чека: {total}')

        discrepancy = calculated_total - total

        if discrepancy == 0:
            print('Расхождений относительно чека нет')

        else:
            print(f'Расхождение относительно чека: {'+' if discrepancy > 0 else ''}{discrepancy}')


if __name__ == "__main__":
    try:
        items, total = read_receipt(path)
    except FileNotFoundError:
        print('Путь к файлу неверный')
    else:
        print_report(items, total)

import pypdf
import re
import logging
from pathlib import Path
from collections.abc import Callable
import csv

logging.getLogger().setLevel(logging.INFO)

Register = list[str | float | None]


def main() -> None:
  folder_path = Path("input")
  registers: list[Register] = []
  for doc in folder_path.iterdir():
    if doc.is_file() and doc.name != ".gitkeep":
      file_extension = doc.suffix
      if file_extension == ".pdf":
        registers.extend(process_pdf(doc))
      elif file_extension == ".csv":
        registers.extend(process_csv(doc))
      else:
        logging.warning(f'Unsupported file extension "{file_extension}" for file "{doc.name}", skipping.')
  save(registers)


def format_money(text: str) -> float:
  return float(
    text.replace("R$", "").replace(".", "").replace(",", ".").replace(" ", "")
  )


def find_monetary(text: str) -> re.Match[str] | None:
  return re.search(r"R\$\s[0-9\.]+,[0-9]{2}", text)


def find_last_payment(text: str) -> re.Match[str] | None:
  return re.search("Pagamento em.+", text)


def add_zero_if_needed(num: int) -> str:
  return str(num).zfill(2)


def find_date(text: str, month: int, year: int) -> str | None:
  match = re.search("^([0-9]{2})\s(\w{3})$", text)
  if not match:
    return None

  matchDay = add_zero_if_needed(int(match.group(1)))
  matchMonth = add_zero_if_needed(month_string_to_number(match.group(2)))
  matchYear = year - 1 if matchMonth == "12" and month == 1 else year
  return f"{matchYear}-{matchMonth}-{matchDay}"


def month_string_to_number(month: str) -> int:
  month_lower = month.lower()
  match month_lower:
    case "jan":
      return 1
    case "fev":
      return 2
    case "mar":
      return 3
    case "abr":
      return 4
    case "mai":
      return 5
    case "jun":
      return 6
    case "jul":
      return 7
    case "ago":
      return 8
    case "set":
      return 9
    case "out":
      return 10
    case "nov":
      return 11
    case "dez":
      return 12
    case _:
      raise ValueError(f'Unknown month string: "{month}"')


def find_postage_date(text: str) -> list[int] | None:
  match = re.search(r"Data de vencimento:\s\d{2}\s(\w{3})\s(\d{4})", text)
  if match:
    month = month_string_to_number(match.group(1))
    year = int(match.group(2))
    return [month, year]
  return None


def get_visitor_body(array: list[str]) -> Callable[..., None]:
  def visitor_body_fn(text: str, _cm: list[int], tm: list[int], _font_dict: dict, _font_size: int) -> None:
    if text.strip() == "":
      return
    y = tm[5]
    if y > 720 or y < 70:
      return
    array.append(text)

  return visitor_body_fn


def process_csv(doc: Path) -> list[Register]:
  doc_name = doc.name
  registers: list[Register] = []
  with open(doc, "r", encoding="utf-8") as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
      date = row[0]
      description = row[1]
      value = float(row[2])
      if description.lower() != "pagamento recebido":
        registers.append(
          [
            doc_name,
            date,
            description,
            value,
          ]
        )

  return registers


def process_pdf(doc: Path) -> list[Register]:
  doc_name = doc.name
  reader = pypdf.PdfReader(doc)
  pages = [i for i in range(4, len(reader.pages))]
  doc_info: dict[str, int | str | None] = {"doc_name": doc_name, "month": None, "year": None, "total_value": 0}

  ## Get month and year
  first_page = reader.pages[0].extract_text().split("\n")
  for line in first_page:
    postage_date = find_postage_date(line)
    if postage_date:
      doc_info["month"], doc_info["year"] = postage_date
      continue
    if find_monetary(line) and doc_info["total_value"] == 0:
      doc_info["total_value"] = format_money(line)
      continue

  ## Get all data from pages with tables
  parts: list[str] = []
  for page in pages:
    page_parts: list[str] = []
    reader.pages[page].extract_text(visitor_text=get_visitor_body(page_parts))
    parts.extend(page_parts)

  logging.debug(f'"{doc.name}" pages: ' + str(len(reader.pages)))
  return process_parts(doc_info, parts)


def process_parts(doc_info: dict[str, int | str | None], parts: list[str]) -> list[Register]:
  doc_name: str = doc_info["doc_name"]
  month: int = doc_info["month"]
  year: int = doc_info["year"]
  total = 0.0
  registers: list[Register] = []
  index = 0
  while index < len(parts):
    if index + 2 >= len(parts):
      logging.error(f'Malformed parts in "{doc_name}": expected groups of 3, got a remainder at index {index}')
      break
    value = format_money(parts[index + 2])
    date = find_date(parts[index], month, year)
    description = parts[index + 1]

    index += 3
    if find_last_payment(description) is None:
      total += value
      registers.append(
        [
          doc_name,
          date,
          description,
          value,
        ]
      )

  total_value: float = doc_info["total_value"]

  if abs(total - total_value) > 0.01:
    logging.error(
      f"Values don't match. Sum: {total}, Total: {total_value}, doc_name: {doc_name}"
    )
    logging.error(list(map(lambda x: f"{x[1]}-{x[2]}-{x[3]}", registers)))

    raise Exception("Values don't match")

  logging.debug(f'"{doc_name}" total value: ' + str(round(total, 2)))
  logging.debug(f'"{doc_name}" registers  : ' + str(len(registers)))
  return registers


def save(registers: list[Register]) -> None:
  sep = ";"
  with open("output/output.csv", "w", encoding="utf-8") as f:
    t = [
      [
        register if isinstance(register, str) else str(register).replace(".", ",")
        for register in row
      ]
      for row in registers
    ]
    data = sep.join(["filename", "date", "description", "value"]) + "\n"
    data += "\n".join([sep.join(register) for register in t])
    f.write(data)

  logging.debug(registers)
  logging.info("total of registers " + str(len(registers)))
  logging.info("total of money " + str(sum([r[-1] for r in registers])))


if __name__ == "__main__":
  main()

import pandas as pd


def dataframe_to_markdown(dataframe: pd.DataFrame, title: str) -> str:
    preview_df = dataframe.head(20).fillna("")
    headers = [str(col) for col in preview_df.columns]
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"

    body_rows = []
    for row in preview_df.itertuples(index=False, name=None):
        values = [str(value).replace("\n", " ").strip() for value in row]
        body_rows.append("| " + " | ".join(values) + " |")

    table_markdown = "\n".join([header_row, separator_row] + body_rows)
    return f"## {title}\n\n{table_markdown}"


def workbook_to_markdown(workbook: dict[str, pd.DataFrame], title: str) -> str:
    sections = [f"# {title}"]
    for sheet_name, sheet_df in workbook.items():
        sections.append(dataframe_to_markdown(sheet_df, sheet_name))
    return "\n\n".join(sections)


def classify_sheet(sheet_name: str) -> str:
    normalized = sheet_name.lower().strip()
    informative_keywords = [
        "lisez",
        "readme",
        "read me",
        "mode d'emploi",
        "instructions",
        "notice",
        "sommaire",
    ]
    if any(keyword in normalized for keyword in informative_keywords):
        return "informatif"
    return "metier"


def filter_business_sheets(workbook: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    business_sheets: dict[str, pd.DataFrame] = {}
    informative_sheets: list[str] = []

    for sheet_name, sheet_df in workbook.items():
        category = classify_sheet(sheet_name)
        if category == "informatif":
            informative_sheets.append(sheet_name)
        else:
            business_sheets[sheet_name] = sheet_df

    if not business_sheets:
        return workbook, informative_sheets

    return business_sheets, informative_sheets

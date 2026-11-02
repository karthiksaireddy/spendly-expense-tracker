#!/usr/bin/env python3
"""Expense Report Generator Skill

Generates monthly and yearly expense reports from the Spendly database.
Outputs markdown reports that can be converted to PDF if needed.

Usage:
    python skills/expense_report.py --user-id <id> --month <YYYY-MM>
    python skills/expense_report.py --user-id <id> --year <YYYY>
    python skills/expense_report.py --user-id <id> --month <YYYY-MM> --output report.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DB_PATH, get_db


def generate_monthly_report(user_id: int, year: int, month: int) -> str:
    """Generate a markdown report for a specific month."""
    db = get_db()
    
    # Get user info
    user = db.execute(
        "SELECT email, display_name FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    
    if not user:
        return f"# Error\n\nUser with ID {user_id} not found."
    
    # Get total for the month
    total = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE user_id = ? AND strftime('%Y', date) = ? AND strftime('%m', date) = ?
        """,
        (user_id, str(year), f"{month:02d}")
    ).fetchone()["total"]
    
    # Get expenses by category
    by_category = db.execute(
        """
        SELECT c.name, SUM(e.amount) as total, COUNT(e.id) as count
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ? AND strftime('%Y', e.date) = ? AND strftime('%m', e.date) = ?
        GROUP BY c.id
        ORDER BY total DESC
        """,
        (user_id, str(year), f"{month:02d}")
    ).fetchall()
    
    # Get all expenses for the month
    expenses = db.execute(
        """
        SELECT e.date, e.amount, e.note, c.name as category
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ? AND strftime('%Y', e.date) = ? AND strftime('%m', e.date) = ?
        ORDER BY e.date DESC
        """,
        (user_id, str(year), f"{month:02d}")
    ).fetchall()
    
    # Generate markdown
    month_name = date(year, month, 1).strftime("%B %Y")
    report = f"# Expense Report: {month_name}\n\n"
    report += f"**User:** {user['display_name']} ({user['email']})\n"
    report += f"**Generated:** {datetime.now().strftime('%d %B %Y at %H:%M')}\n\n"
    
    report += "## Summary\n\n"
    report += f"- **Total Spending:** ₹{total:,.2f}\n"
    report += f"- **Number of Transactions:** {len(expenses)}\n"
    report += f"- **Categories Used:** {len(by_category)}\n\n"
    
    report += "## Spending by Category\n\n"
    report += "| Category | Total | Count |\n"
    report += "|----------|-------|-------|\n"
    for cat in by_category:
        report += f"| {cat['name']} | ₹{cat['total']:,.2f} | {cat['count']} |\n"
    report += "\n"
    
    report += "## All Transactions\n\n"
    report += "| Date | Category | Amount | Note |\n"
    report += "|------|----------|--------|------|\n"
    for exp in expenses:
        note = exp['note'] or "-"
        report += f"| {exp['date']} | {exp['category']} | ₹{exp['amount']:,.2f} | {note} |\n"
    
    return report


def generate_yearly_report(user_id: int, year: int) -> str:
    """Generate a markdown report for a specific year."""
    db = get_db()
    
    # Get user info
    user = db.execute(
        "SELECT email, display_name FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    
    if not user:
        return f"# Error\n\nUser with ID {user_id} not found."
    
    # Get total for the year
    total = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE user_id = ? AND strftime('%Y', date) = ?
        """,
        (user_id, str(year))
    ).fetchone()["total"]
    
    # Get monthly totals
    monthly = db.execute(
        """
        SELECT strftime('%m', date) as month, SUM(amount) as total, COUNT(*) as count
        FROM expenses
        WHERE user_id = ? AND strftime('%Y', date) = ?
        GROUP BY strftime('%m', date)
        ORDER BY month
        """,
        (user_id, str(year))
    ).fetchall()
    
    # Get expenses by category for the year
    by_category = db.execute(
        """
        SELECT c.name, SUM(e.amount) as total, COUNT(e.id) as count
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ? AND strftime('%Y', e.date) = ?
        GROUP BY c.id
        ORDER BY total DESC
        """,
        (user_id, str(year))
    ).fetchall()
    
    # Generate markdown
    report = f"# Annual Expense Report: {year}\n\n"
    report += f"**User:** {user['display_name']} ({user['email']})\n"
    report += f"**Generated:** {datetime.now().strftime('%d %B %Y at %H:%M')}\n\n"
    
    report += "## Summary\n\n"
    report += f"- **Total Spending:** ₹{total:,.2f}\n"
    report += f"- **Number of Transactions:** {sum(m['count'] for m in monthly)}\n"
    report += f"- **Categories Used:** {len(by_category)}\n\n"
    
    report += "## Monthly Breakdown\n\n"
    report += "| Month | Total | Count |\n"
    report += "|-------|-------|-------|\n"
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in monthly:
        month_idx = int(m['month']) - 1
        report += f"| {month_names[month_idx]} {year} | ₹{m['total']:,.2f} | {m['count']} |\n"
    report += "\n"
    
    report += "## Spending by Category\n\n"
    report += "| Category | Total | Count |\n"
    report += "|----------|-------|-------|\n"
    for cat in by_category:
        report += f"| {cat['name']} | ₹{cat['total']:,.2f} | {cat['count']} |\n"
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Generate expense reports from Spendly database"
    )
    parser.add_argument("--user-id", type=int, required=True, help="User ID to generate report for")
    parser.add_argument("--month", type=str, help="Month in YYYY-MM format")
    parser.add_argument("--year", type=int, help="Year in YYYY format")
    parser.add_argument("--output", type=str, help="Output file path (default: stdout)")
    
    args = parser.parse_args()
    
    if not args.month and not args.year:
        parser.error("Either --month or --year must be specified")
    
    if args.month and args.year:
        parser.error("Specify either --month or --year, not both")
    
    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
            report = generate_monthly_report(args.user_id, year, month)
        except ValueError:
            parser.error("Month must be in YYYY-MM format")
    else:
        report = generate_yearly_report(args.user_id, args.year)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report saved to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

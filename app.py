import streamlit as st
import requests
import json
import csv
from datetime import datetime, timedelta
import os
from dateutil import parser

# Replace these with your own values or set them as environment variables
SUBDOMAIN = os.getenv("SUPPORTBEE_SUBDOMAIN", "YOUR_SUBDOMAIN")
API_TOKEN = os.getenv("SUPPORTBEE_API_TOKEN", "YOUR_API_TOKEN")

# API base URL
BASE_URL = f"https://{SUBDOMAIN}.supportbee.com"

# Headers for API requests
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def fetch_all_tickets(start_date, end_date):
    all_tickets = []
    page = 1
    while True:
        url = (
            f"{BASE_URL}/tickets"
            f"?auth_token={API_TOKEN}"
            f"&since={start_date}"
            f"&until={end_date}"
            f"&page={page}"
            f"&sort_by=last_activity"
        )
        response = requests.get(url, headers=HEADERS)
        
        # Check if the request is successful
        if response.status_code != 200:
            st.error(f"Error fetching tickets: {response.status_code}")
            st.write(response.text)  # Log the response body for debugging
            break
        
        data = response.json()
        tickets = data.get("tickets", [])
        st.write(f"Page {page} response:", data)  # Log full response for each page
        
        if not tickets:
            break
        all_tickets.extend(tickets)
        page += 1
    return all_tickets

def fetch_replies(ticket_id):
    url = f"{BASE_URL}/tickets/{ticket_id}/replies?auth_token={API_TOKEN}"
    response = requests.get(url, headers=HEADERS)
    
    # Log replies to ensure the data is being returned correctly
    if response.status_code != 200:
        st.error(f"Error fetching replies for ticket {ticket_id}: {response.status_code}")
        st.write(response.text)  # Log the response body for debugging
        return []
    
    st.write(f"Replies for ticket {ticket_id}: ", response.json())  # Log the replies for each ticket
    return response.json().get("replies", [])


def safe_get(dictionary, keys, default=''):
    for key in keys:
        if isinstance(dictionary, dict):
            dictionary = dictionary.get(key, {})
        else:
            return default
    return dictionary if dictionary != {} else default

def create_csv(tickets):
    import io
    output = io.StringIO()
    
    # Defining the fixed column headers
    fieldnames = [
        'ticket_id', 'date', 'labels', 'ticket_description',
        'assigned_agent_name', 'first_response_time', 'average_response_time'
    ]
    
    # Dynamically add reply columns based on the maximum number of replies
    max_replies = max(len(ticket.get('replies', [])) for ticket in tickets)
    for i in range(max_replies):
        fieldnames.append(f'agent_{i}')
        fieldnames.append(f'customer_{i}')
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for ticket in tickets:
        ticket_id = ticket.get('id', '')
        date_str = ticket.get('last_activity_at', '')
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ').strftime('%m-%d-%Y') if date_str else ''
        
        labels = [label.get('name', '') for label in ticket.get('labels', [])]
        ticket_description = safe_get(ticket, ['content', 'text'], default='')

        # Extract assigned agent name
        assigned_agent_name = safe_get(ticket, ['current_user_assignee', 'name'], default='Unassigned')

        # Calculate response times based on replies
        ticket_created_at_str = ticket.get('created_at', '')
        ticket_created_at = parser.parse(ticket_created_at_str) if ticket_created_at_str else None
        
        first_agent_reply_time = None
        response_times = []
        previous_message_time = ticket_created_at

        replies = ticket.get('replies', [])
        agent_reply_count = 0
        customer_reply_count = 0

        row_data = {
            'ticket_id': ticket_id,
            'date': date,
            'labels': ', '.join(labels),
            'ticket_description': ticket_description,
            'assigned_agent_name': assigned_agent_name,
        }

        # Loop through replies and assign to the appropriate agent/customer fields
        for i, reply in enumerate(sorted(replies, key=lambda x: x.get('created_at', ''))):
            reply_created_at_str = reply.get('created_at', '')
            reply_created_at = parser.parse(reply_created_at_str) if reply_created_at_str else None

            # Check if it's an agent or customer reply
            if reply.get('agent'):
                row_data[f'agent_{agent_reply_count}'] = safe_get(reply, ['content', 'text'], default='')
                agent_reply_count += 1
            else:
                row_data[f'customer_{customer_reply_count}'] = safe_get(reply, ['content', 'text'], default='')
                customer_reply_count += 1

            # Calculate response time for agents
            if reply_created_at and previous_message_time:
                time_diff = (reply_created_at - previous_message_time).total_seconds() / 3600
                if reply.get('agent'):
                    response_times.append(time_diff)
                    if not first_agent_reply_time:
                        first_agent_reply_time = reply_created_at
                previous_message_time = reply_created_at

        # Calculate first and average response times
        first_response_time = (first_agent_reply_time - ticket_created_at).total_seconds() / 3600 if ticket_created_at and first_agent_reply_time else None
        average_response_time = sum(response_times) / len(response_times) if response_times else None

        row_data['first_response_time'] = first_response_time
        row_data['average_response_time'] = average_response_time

        writer.writerow(row_data)

    return output.getvalue()


def main():
    st.title("Support Ticket Downloader")

    # Date input


    
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    end_date = st.date_input("End Date", datetime.now())

    # Convert dates to the required format
    start_date_str = start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_date_str = end_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    st.write(f"Start date: {start_date_str}, End date: {end_date_str}")  # Log the date values

    if st.button("Fetch and Download Tickets"):
        with st.spinner("Fetching tickets..."):
            tickets = fetch_all_tickets(start_date_str, end_date_str)
            if not tickets:
                st.warning("No tickets found for the selected date range.")
                return

            # Fetch replies for each ticket
            for ticket in tickets:
                ticket_id = ticket["id"]
                replies = fetch_replies(ticket_id)
                ticket["replies"] = replies

            # Create CSV content
            csv_content = create_csv(tickets)

            # Provide download link
            st.success(f"Fetched {len(tickets)} tickets.")
            st.download_button(
                label="Download Tickets CSV",
                data=csv_content,
                file_name='tickets.csv',
                mime='text/csv',
            )

if __name__ == "__main__":
    main()

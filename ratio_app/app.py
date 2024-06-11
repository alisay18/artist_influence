import threading
from flask import Flask, request, render_template, redirect, url_for, send_file
import pandas as pd
import time
import ratio_calculator as rc

app = Flask(__name__, template_folder='templates')
campaigns = pd.DataFrame(columns=['URL', 'Genre', 'Views', 'Comments', 'Likes', 'Status', 'Views_Generated', 'Likes_Generated', 'Comments_Generated'])
running = True

def load_csv(file_path):
    return pd.read_csv(file_path)

def process_campaign():
    global running
    while running:
        for index, row in campaigns.iterrows():
            if row['Status'] == 'Active':
                stats = rc.get_video_details(row['URL'])
                views = stats['views']
                expected_likes = views * 0.1  # Example ratio
                expected_comments = views * 0.02  # Example ratio
                likes_needed = max(0, int(expected_likes - row['Likes']))
                comments_needed = max(0, int(expected_comments - row['Comments']))
                comments = row['Comments'].split(';')
                rc.drip_engagement(row['URL'], likes_needed, comments_needed, comments[:comments_needed])
                campaigns.at[index, 'Likes_Generated'] += likes_needed
                campaigns.at[index, 'Comments_Generated'] += comments_needed
        time.sleep(3600)

@app.route('/')
def index():
    return render_template('index.html', tables=[campaigns.to_html(classes='data', header="true")])

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    global campaigns
    new_data = load_csv(file)
    campaigns = pd.concat([campaigns, new_data], ignore_index=True)
    return redirect(url_for('index'))

@app.route('/start_campaign/<int:campaign_id>')
def start_campaign(campaign_id):
    campaigns.at[campaign_id, 'Status'] = 'Active'
    return redirect(url_for('index'))

@app.route('/stop_campaign/<int:campaign_id>')
def stop_campaign(campaign_id):
    campaigns.at[campaign_id, 'Status'] = 'Completed'
    return redirect(url_for('index'))

@app.route('/export')
def export():
    campaigns.to_csv('campaigns_report.csv', index=False)
    return send_file('campaigns_report.csv', as_attachment=True)

@app.route('/stop')
def stop():
    global running
    running = False
    return redirect(url_for('index'))

@app.route('/start')
def start():
    global running
    running = True
    threading.Thread(target=process_campaign).start()
    return redirect(url_for('index'))

if __name__ == "__main__":
    threading.Thread(target=process_campaign).start()
    app.run(debug=True)

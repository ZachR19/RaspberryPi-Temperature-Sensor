import Adafruit_DHT as dht
import json, time, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from os.path import expanduser #for getting user home directory
from ISStreamer.Streamer import Streamer

#-------- Global Variables ------
#The raspberry pi pin that is sending data, in this case it is pin #7 but is labeled as GPIO 4
DHT = 4

#Last time an email was sent
last_email_time = None

#local paths to config files
emails_filepath = "/bin/tempsensor/emails" #who to notify of temperature changes
log_filepath = expanduser("~") + "/Desktop/temperatureLog" #logfile
#-------------------------------

class EmailContents:
	def __init__(self, emails, temp, humidity, time_occurred, notify_interval):
		self.emails = emails
		self.temp = temp
		self.humidity = humidity
		self.time = time_occurred
		self.send_interval = notify_interval

def appendLog(message):
	with open(log_filepath, "a") as file:
		file.write(str(message) + "\n")

	print(message)

def getSetting(varName):
	try:
		with open("settings.json", "r") as file:
			data = json.load(file)

			return data[varName]
	except Exception as e:
		appendLog(e)

def getEmailList():
	file = open(emails_filepath, "r")
	lstEmails = []

	with open(emails_filepath, "r") as file:
		for line in file:
			if line != "":
				lstEmails.append(line.rstrip())

	return lstEmails

def getSMTPServer():
	#Attempt server login
	login_success = False

	while login_success == False:
		try:
			login_as = getSetting('email_sender')

			#Create server connection via gmails smtp server
			server = smtplib.SMTP("smtp.gmail.com", 587)

			server.ehlo()
			server.starttls()
			server.ehlo()

			#login
			server.login(login_as, getSetting('email_password'))

			login_success = True

		except Exception as e:
			appendLog(e)
			print("login failed. Waiting 10 seconds before next attempt")
			time.sleep(10)

		if login_success:
			appendLog("login to email account " + login_as + " succeeded.")
			return server
			break

def buildHTMLEmail(contents):
	#build list of users to notify
	list_emails = ""
	template = ""

	for user in contents.emails:
		list_emails += "<li>" + user + "</li>"

	try:
		with open('email_template.html', 'r') as email_template:
			template = email_template.read()
			template = template.format(list_emails = list_emails, temp = contents.temp, humidity = contents.humidity, date = contents.time, min_temp = getSetting('min_temp'), max_temp = getSetting('max_temp'), min_humidity = getSetting('min_humidity'), max_humidity = getSetting('max_humidity'), min_notify = contents.send_interval)
	except Exception as e:
		appendlog(e)

	return template

def sendEmails(server, emailContents):
	global last_email_time

	html_message = buildHTMLEmail(emailContents)

	msg = MIMEText(html_message, 'html')
	msg['Subject'] = 'Temperature Warning'
	msg['From'] = getSetting('email_sender')

	try:
		#Send email
		for email in emailContents.emails:
			msg['To'] = email
			server.sendmail(getSetting('email_sender'), email, msg.as_string())

			appendLog("Warning email sent to " + email + " at " + str(datetime.now()) + "\n") 

		server.quit()
		last_email_time = datetime.now()
	except Exception as e:
		appendLog(e)

def shouldSendEmail():
	global last_email_time

	#if this is the very first email, send it and wait
	if last_email_time == None:
		return True

	#calculate time since last email
	date_diff = datetime.now() - last_email_time
	diff_seconds = date_diff.total_seconds()
	diff_mins = diff_seconds/60

	#if greater than minutes_between_emails, send another email
	mins_between = getSetting('mins_between_emails')
	if diff_mins >= mins_between:
		return True
	else:
		appendLog("waiting " + str(round((mins_between - diff_mins),2)) + " minutes to send next email \n")
		return False

def trySendEmail(temp_f, humidity):
	if shouldSendEmail():
		server = getSMTPServer()
		emails = getEmailList()
		contents = EmailContents(emails, temp_f, humidity, datetime.now(), getSetting("mins_between_emails"))
		sendEmails(server, contents)

#Main program ---------------------------------------------------
appendLog("\nProgram started at " + str(datetime.now()))

#InitialState Streaming object
streamer = Streamer(bucket_name=getSetting('BUCKET_NAME'), bucket_key=getSetting('BUCKET_KEY'), access_key=getSetting('ACCESS_KEY'))

while True:
	try:
		humidity,temp_c = dht.read_retry(dht.DHT22, DHT)

		if humidity is not None and temp_c is not None:
			#Calulate temperature in Fahrenheit
			temp_f = format(temp_c * 9.0 / 5.0 + 32.0, ".2f")
			streamer.log("Temperature(F)", temp_f)
			print("Temperature(F): " + temp_f)

			#Format humidity
			humidity = format(humidity, ".2f")
			streamer.log("Humidity(%)", humidity)
			print("Humidity(%): " + humidity + "\n")

			#Flush data to the InitialStreamer
			streamer.flush()

			#Temperature check
			if getSetting('send_temp_warnings'):
				if float(temp_f) >= getSetting('max_temp'):
					appendLog("Temperature has gone above the recommended level at " + str(datetime.now()))

					trySendEmail(temp_f, humidity)
				elif float(temp_f) < getSetting('min_temp'):
					appendLog("Temperature has fallen below the recommended level at" + str(datetime.now()))

					trySendEmail(temp_f, humidity)

			#Humidity check
			if getSetting('send_humidity_warnings'):
				if float(humidity) >= getSetting('max_humidity'):
					appendLog("Humidity has gone above the recommended level at " + str(datetime.now()))

					trySendEmail(temp_f, humidity)
				elif float(humidity) < getSetting('min_humidity'):
					appendLog("Humidity has fallen below the recommended level at " + str(datetime.now()))

					trySendEmail(temp_f, humidity)
		else:
			appendLog("Sensor cannot get a reading...trying again...")

		#wait before reading the temperature again
		time.sleep(int(getSetting('secs_between_reads')))
	except Exception as e:
		appendLog(e)
		continue

#!/usr/bin/env python
PKG = "cob_laser_calibration"
NODE = "determine_calibration_object_pose"

### DETAILS ###
# Script: Detect the pose of the calibration object with respect to the base
# Author: Daniel Maeki (ipa-fxm-dm)
# Supervisor: Felix Messmer (ipa-fxm)

### IMPORTS ###
import roslib; roslib.load_manifest(PKG)
import rospy
import tf
from math import pi
from sensor_msgs.msg import LaserScan
from visualize_laser_scan import Get_laserscan, Visualize_laserscan
from detect_cylinders import Detect_calibration_object
from pose_to_checkerboard_points import Convert_cal_obj_pose

### GLOBAL VARIABLES ###
scanner_location = 'front'												# Specify 'front' or 'rear' for the location of the laser scanner
resolution = 1000														# Resolution of the laser scan image (setting the resolution higher will improve the accuracy)
scan_amount = 20														# Amount of scans to be merged for average scan
success_amount = 6														# Amount of succeeded detections needed for completion
fail_amount = success_amount * 11										# Amount of failed detections needed for returning a failed result.
border = 100															# Border of pixels around the image
max_laser_point_dist = 3.2												# Maximum range of each laser point in meters
line_color = (0, 255, 255)												# Color of line that will help detecting the calibration object
cylinder = {}															# Properties of the cylinders from the calibration object in meters
cylinder["radii"] = (0.03*resolution, 0.06*resolution, 0.09*resolution)		# Radii of cylinders (small, medium=2*small, large=3*small)
cylinder["angles"] = (7*pi/6, 11*pi/6, 1*pi/2)								# Angles of cylinders (small, medium, large) with respect to calibration object centre
cylinder["height"] = 0.2													# Height of the cylinders
cylinder["dist"] = 0.4*resolution											# Distance between the centers of the cylinders

### POSSIBLE_IMPROVEMENTS ###
# ---

### TODO ###
# ---


### SCRIPT ###
class Detect_cal_obj_pose():
	# 0. Init is the first function that is run in every class. Here we set the needed variables to their initial values.
	def __init__(self):
		rospy.init_node(NODE)
		scan = None
		image = None
		try:
			assert scanner_location == 'front' or scanner_location == 'rear'
		except(AssertionError):
			print "\n\n\n--> The laser scanner location is not set to either 'front' or 'rear'"
			print "--> Modify this in 'determine_cal_obj_pose.py' located in the 'cob_laser_calibration' package\n\n\n"
			exit()

	def callback(self, data):
		self.laserscan = data

	def run(self):
		
		print "\n\n\n>>> Start \n\n\n"
		
		# Activate transform listener
		tf_listener = tf.TransformListener()
		
		# 1. Get pose of laser scanner with respect to base
		try:
			tf_listener.waitForTransform('/base_footprint', '/base_laser_'+scanner_location+'_link', rospy.Time(), rospy.Duration(1))
			laserscan_pose = tf_listener.lookupTransform('/base_footprint', '/base_laser_'+scanner_location+'_link', rospy.Time())
			#print "laserscan_pose: ", laserscan_pose
		except(tf.Exception), e:
			print "Laser scan transform not available, aborting..."
			print "Error message: ", e
			exit()
		
		# 2. Get raw data from laser scanner, create callback function
		try:
			rospy.Subscriber('/scan_'+scanner_location, LaserScan, self.callback)
			rospy.wait_for_message('/scan_'+scanner_location, LaserScan, timeout=2)
		except(rospy.ROSException), e:
			print "Laser scan topic not available, aborting..."
			print "Error message: ", e
			exit()
		
		# 3. Loop calibration object detection until either the success_counter or the fail_counter exceeds its limit
		successful_detections = []
		succes_counter = 0
		fail_counter = 0
		while succes_counter < success_amount and fail_counter < fail_amount:
			# 4. Get average scan (amount of scans is specified in scan_amount) and remove all null detections
			laserscan_data = Get_laserscan()
			while laserscan_data.get_count() < scan_amount:
				laserscan_data.append_laserscan(self.laserscan)
				# Creates a brief period between each laser scan allowing more variation
				rospy.sleep(0.01)
			scan = laserscan_data.get_result()
			print "--> Scan received "
			
			# 5. Create and draw an image from the laser scan data
			visualize = Visualize_laserscan(resolution, border, max_laser_point_dist, laserscan_pose, cylinder, line_color)
			image, origin = visualize.convert_to_image(scan)
			print "--> Image received"
				
			# 6. Find the calibration object from the image and determine it's x, y and yaw coordinates with respect to the laser scanner
			detect = Detect_calibration_object(resolution, origin, cylinder, line_color)
			image, cal_obj_pose = detect.detect_cal_object(image)
			#print "cal_obj_pose: ", cal_obj_pose
				
			# 7. Convert the calibration object pose with respect to the laser scanner into Euler coordinates with respect to the base
			if cal_obj_pose is not None:
				# 7. Depending on the 'front' or 'rear' laser scanner, we add or subtract the base position to/from the calibration object pose
				if scanner_location == 'front':
					cal_obj_position = [cal_obj_pose[0]+laserscan_pose[0][0], cal_obj_pose[1]+laserscan_pose[0][1], cylinder["height"]]
				elif scanner_location == 'rear':
					cal_obj_position = [-cal_obj_pose[0]+laserscan_pose[0][0], -cal_obj_pose[1]+laserscan_pose[0][1], cylinder["height"]]
				cal_obj_rotation = [0, 0, cal_obj_pose[2]]
				cal_obj_pose = [cal_obj_position, cal_obj_rotation]
				# Calibration object pose converted into Euler coordinates
				successful_detections.append(cal_obj_pose)
				
				# If a successful detection was made, increment succes_counter
				succes_counter += 1
				print "--> SUCCESFULLY received calibration object pose\n"
				print "! SUCCES_counter = %i\n\n" %succes_counter
			else:
				# If the detect_cal_object returned an empty cal_obj_pose, then increment fail_counter
				fail_counter += 1
				print "--> FAILED to receive calibration object pose\n"
				print "! FAIL_counter = %i\n\n" %fail_counter
		
		# 8. Calculate average of all successful detections
		avg_calibration_object_pose = [[0,0,0],[0,0,0]]
		counter = 0
		for detection in successful_detections:
			for i in range(0,len(detection)):
				for j in range(0,len(detection[i])):
					avg_calibration_object_pose[i][j] = (avg_calibration_object_pose[i][j] * counter + detection[i][j]) / (counter + 1)
			counter += 1
		
		# 9. Calculate standard deviation of all successful detections
		deviation = [[0,0,0],[0,0,0]]
		counter = 0
		for detection in successful_detections:
			for i in range(0,len(detection)):
				for j in range(0,len(detection[i])):
					deviation[i][j] = (deviation[i][j] * counter + (detection[i][j] - avg_calibration_object_pose[i][j])) / (counter + 1)
			counter += 1
		
		# Convert the detected calibration object pose into the checkerboard points
		convert = Convert_cal_obj_pose(avg_calibration_object_pose)
		checkerboard_points = convert.pose_to_points()
		
		# 10. Print and display results
		if fail_counter == fail_amount:
			print "\n\n>>> FAILED to detect calibration object pose successfully"
		elif succes_counter == success_amount:
			print "\n\n>>> SUCCEEDED to detect calibration object pose successfully"
		print "\n\nSuccessful_detections:"
		for detection in successful_detections:
			print detection
		print "\n\nCalibration object pose:"
		print avg_calibration_object_pose
		print "\n\nStandard deviation:"
		print deviation
		print "\n\nCheckerboard_points:"
		for point in checkerboard_points:
			print point
		if fail_counter == fail_amount:
			print "\n\n>>> FAILED to detect calibration object pose successfully"
		elif succes_counter == success_amount:
			print "\n\n>>> SUCCEEDED to detect calibration object pose successfully"
		print "\n\n\n>>> End \n\n\n"
		# Only view the image if the resolution is under 200 because the image becomes too large for viewing if the resolution is above 200
		if resolution <= 200:
			# Set the calibration object pose for the image and draw the calibration object in the image
			cal_obj_pose_for_img = -avg_calibration_object_pose[0][0], -avg_calibration_object_pose[0][1], -avg_calibration_object_pose[1][2]
			image = visualize.draw_calibration_object(image, cal_obj_pose_for_img)
			print "Select the image window and press a key to exit\n"
			# View image
			visualize.show_image(image)


### MAIN ###
if __name__ == "__main__":
	l = Detect_cal_obj_pose() # init
	l.run() # run


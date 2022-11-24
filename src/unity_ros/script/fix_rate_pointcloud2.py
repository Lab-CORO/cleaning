#!/usr/bin/env python3

import rospy
from rospy import Publisher
from sensor_msgs.msg import PointCloud2

def callback(msg):
    """ 
    Get the message of a topic and publish it at a fix frequence
    :param msg: Depth perception of a camera
    :type msg: Pointcloud2
    """
    pub = rospy.Publisher('fix_rate_pointcloud2', PointCloud2,queue_size=1)
    rospy.loginfo(msg.header)
    
    pub.publish(msg)
    rospy.sleep(1) # Wait time to publish at a fix frequence

def fix_rate_pointcloud2():
    """
    Subscribe to a pointcloud2 topic to republish it at a lower frequence
    """
    rospy.init_node('fix_rate_pointcloud2')
    rospy.Subscriber("/camera/depth/color/points", PointCloud2, callback, queue_size=1) 
    rospy.spin()

if __name__ == '__main__':
    fix_rate_pointcloud2()

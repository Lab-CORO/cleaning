#!/usr/bin/env python3
import math

import rospy
import rospkg
from std_msgs.msg import String
import open3d as o3d
from std_msgs.msg import Float64MultiArray
from std_msgs.msg import MultiArrayDimension
from sensor_msgs.msg import PointCloud2
from open3d_ros_helper import open3d_ros_helper as o3d_ros
from rospy.numpy_msg import numpy_msg
from rospy_tutorials.msg import Floats
import numpy as np
from math import radians, degrees
import copy
import time
import tf2_ros
import tf
import tf2_geometry_msgs
from geometry_msgs.msg import PoseStamped

result_pub = rospy.Publisher('/pcl_result', PointCloud2, queue_size=10)

# Load the machne in pcd
machine_path = rospkg.RosPack().get_path('utility') + "/mesh/scie1.ply"
machine_pcd = o3d.io.read_point_cloud(machine_path)
machine_np = np.asarray(machine_pcd.points)

# Generate the cone parameters
cone_z = 0.5
cone_alpha = radians(30)  # fov min /2
cone_r = cone_z * math.tan(cone_alpha)
cone_np = np.array([[0, 0, 0], [0, 0, cone_z]])
cone_pcd = o3d.geometry.PointCloud()
cone_pcd.points = o3d.utility.Vector3dVector(cone_np)

# Debug
debug = False

if debug:
    mesh_cone = o3d.geometry.TriangleMesh.create_cone(radius=cone_r, height=cone_z)
    R = mesh_cone.get_rotation_matrix_from_xyz((np.pi, 0, 0))
    mesh_cone.rotate(R, center=(0, 0, 0))
    mesh_cone.translate((0, 0, cone_z))





def callback(msg):
    start_time = time.time()
    # open cone pcd + machine pcd
    mat = np.asarray(msg.data)
    mat.resize(4, 4)

    # cone is a pcd with 2pts as the top of the cone and the bot
    cone_t = copy.deepcopy(cone_pcd)
    cone_t_np = np.asarray(cone_t.points)
    if debug:
        cone_t.paint_uniform_color([0, 0, 1])
        machine_pcd.paint_uniform_color([1, 0, 0])
        mesh_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(
            size=0.06, origin=[0, 0, 0])

    tf_buffer = tf2_ros.Buffer()
    listener = tf2_ros.TransformListener(tf_buffer)

    try:
        trans_cone = tf_buffer.lookup_transform('cone', 'machine', rospy.Time(),
                                                rospy.Duration(1.0))
    except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
            tf2_ros.ExtrapolationException):
        rospy.loginfo("pb dans la transformation")

    try:
        trans_machine = tf_buffer.lookup_transform('machine', 'cone', rospy.Time(),
                                                   rospy.Duration(1.0))
    except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
            tf2_ros.ExtrapolationException):
        rospy.loginfo("pb dans la transformation")

    pts_include = []

    # for each pts in the machine we create the 2 vector: cone a->b and a->pt
    # with the dot product we get the angle and then the norme of the two
    for pt in machine_np:

        pose = PoseStamped()
        pose.pose.position.x = pt[0]
        pose.pose.position.y = pt[1]
        pose.pose.position.z = pt[2]
        pose.pose.orientation.x = 0
        pose.pose.orientation.y = 0
        pose.pose.orientation.z = 0
        pose.pose.orientation.w = 1

        pt = tf2_geometry_msgs.do_transform_pose(pose, trans_cone)

        norm = math.sqrt(pow(cone_t_np[0][0] - pt.pose.position.x, 2) +
                         pow(cone_t_np[0][1] - pt.pose.position.y, 2) +
                         pow(cone_t_np[0][2] - pt.pose.position.z, 2))

        if norm <= cone_z:
            eq_cone = pow(cone_t_np[0][0] - pt.pose.position.x, 2) + \
                      pow(cone_t_np[0][1] - pt.pose.position.y, 2) - \
                      (pow(cone_t_np[0][2] - pt.pose.position.z, 2) * pow((cone_r / cone_z), 2))

            if eq_cone <= 0:
                pt = tf2_geometry_msgs.do_transform_pose(pt, trans_machine)
                pts_include.append([pt.pose.position.x, pt.pose.position.y, pt.pose.position.z])

    pts_include_np = np.asarray(pts_include)

    pts_include_pcd = o3d.geometry.PointCloud()
    if pts_include:
        pts_include_pcd.points = o3d.utility.Vector3dVector(pts_include_np)
        if debug:
            print("--- %s seconds ---" % (time.time() - start_time))
            pts_include_pcd.paint_uniform_color([1, 0, 0])
            cone_t = copy.deepcopy(cone_pcd).transform(mat)
            mesh_cone_t = copy.deepcopy(mesh_cone).transform(mat)
            cone_t.paint_uniform_color([0, 0, 1])
            o3d.visualization.draw_geometries([pts_include_pcd, cone_t, mesh_cone_t])
    pcd = o3d_ros.o3dpc_to_rospc(pts_include_pcd)
    pcd.header.frame_id = "machine"
    result_pub.publish(pcd)



if __name__ == '__main__':
    rospy.init_node('cone', anonymous=True)
    rospy.Subscriber("/transf_mat", Float64MultiArray, callback)

    rospy.spin()
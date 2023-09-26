#!/usr/bin/env python3

import pickle

import geometry_msgs.msg
import numpy as np
import rospkg
import rospy
import tf2_geometry_msgs
import tf2_ros
from geometry_msgs.msg import PoseStamped, Pose, Pose2D
from open3d_ros_helper import open3d_ros_helper as o3d_ros
from ros_numpy import numpify
from sensor_msgs.msg import Image
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from std_msgs.msg import Float64MultiArray
from utility.doosan import Doosan
from utility.rviz_tool import display_marker_array
from tf.transformations import euler_from_quaternion
from visualization_msgs.msg import Marker
from scipy.spatial.transform import Rotation as R
from data_manager import DataManager
from open3d_tools import Open3dTool
from robot import Robot
from dust import Dust
from tf_tools import TfTools
from utility.srv import DetectDust
from python_tsp.distances import euclidean_distance_matrix


class OnlineStrategy:
    def __init__(self, path_machine, offline_trajectory_path):
        # Callback ROS
        self.image_sub = rospy.Subscriber("/rgb/image_raw", Image, self.callback_color)
        self.depth_sub = rospy.Subscriber("/depth_to_rgb/image_raw", Image, self.callback_depth)

        # Publisher
        self.pcl_pub = rospy.Publisher('/transf_mat', Float64MultiArray, queue_size=10)

        # Pub telemetrie
        self.guard_pub = rospy.Publisher('/telemetrie/guard', JointState, queue_size=10)
        self.dust_pub = rospy.Publisher('/telemetrie/dust_pose', PoseStamped, queue_size=10)
        self.finish_pub = rospy.Publisher('/telemetrie/finish', Bool, queue_size=10)
        self.octo_pub = rospy.Publisher('/toggle_octomap', Bool, queue_size=10)
        self.spot_pub = rospy.Publisher('/telemetrie/spot', Pose2D, queue_size=10)
        # Dicts
        with open(offline_trajectory_path, 'rb') as f:
            self.offline_traj = pickle.load(f)

        # Global var
        self.base_trajectory = list(map(list, list(self.offline_traj.keys())))
        print(self.base_trajectory)
        self.depth_image = None
        self.color_image = None

        self.tf_buffer = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.tf_buffer)

        self.broadcaster_robot = tf2_ros.StaticTransformBroadcaster()
        self.broadcaster = tf2_ros.StaticTransformBroadcaster()

        self.arm = Doosan()
        self.data_manager = DataManager()
        self.open3d_tool = Open3dTool()
        self.robot = Robot()
        self.dust = Dust()
        self.tf_tools = TfTools()
        print("online ready")

    def callback_color(self, img):
        self.color_image = img

    def callback_depth(self, img):
        self.depth_image = img

    # def ask_dust_poses(self):
    #     """
    #     retrun a list a positions in the vacuum_tcp frame
    #     """
    #     rospy.wait_for_service('/detect_dust', timeout=5)
    #     result_poses = []
    #     try:
    #         detect_dust = rospy.ServiceProxy('/detect_dust', DetectDust)
    #
    #         resp1 = detect_dust(self.color_image, self.depth_image)
    #
    #         pcd_dust = o3d_ros.rospc_to_o3dpc(resp1.pcds[0])
    #         # mesh = o3d.geometry.TriangleMesh.create_coordinate_frame()
    #         dust_poses = np.asarray(pcd_dust.points)
    #
    #         # Transform to robot frame
    #         frame = resp1.pcds[0].header.frame_id
    #         try:
    #             trans_camera = tf_buffer.lookup_transform('vacuum_tcp', frame, rospy.Time(),
    #                                                       # why not direct the world frame ?
    #                                                       rospy.Duration(1.0))
    #         except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
    #                 tf2_ros.ExtrapolationException):
    #             rospy.loginfo('{nodeName} : Aucun message de la transformation'.format(nodeName=rospy.get_name()))
    #         for pt in dust_poses:
    #             pose = geometry_msgs.msg.PoseStamped()
    #             pose.pose.position.x = pt[0]
    #             pose.pose.position.y = pt[1]
    #             pose.pose.position.z = pt[2]
    #             pose.pose.orientation.w = 1.0
    #             pose.header.frame_id = frame
    #
    #             pose = tf2_geometry_msgs.do_transform_pose(pose, trans_camera)
    #
    #             result_poses.append(numpify(pose.pose.position)[:3])
    #
    #     except rospy.ServiceException as e:
    #         print("Service call failed: %s" % e)
    #     return result_poses

    # def filter_dust(self, points, dist=0.4):
    #     """
    #     get points list in stampted points and return the same
    #     """
    #     # print(points)
    #     np_points = []
    #     for point in points:
    #         # point = numpify(point.pose.position)
    #         np_points.append([point[0], point[1], point[2]])
    #
    #     np_points = np.asarray(np_points)
    #     # print(np_points)
    #     norm = np.linalg.norm(np_points, axis=1)
    #     # print(norm)
    #     selected_points = np_points[norm < dist]
    #     return selected_points


if __name__ == '__main__':
    global color_image, depth_image
    rospy.init_node('online_strategie', anonymous=True)

    traj_path = rospkg.RosPack().get_path('cleaning') + rospy.get_param("/trajectorie")
    machine_pcd_path = rospkg.RosPack().get_path('cleaning') + rospy.get_param("/machine_pcd")

    debug = rospy.get_param("/debug", default=False)

    broadcaster_guard = tf2_ros.StaticTransformBroadcaster()
    tf_buffer = tf2_ros.Buffer()
    listener = tf2_ros.TransformListener(tf_buffer)

    strat = OnlineStrategy(machine_pcd_path, traj_path)
    rospy.sleep(1)
    is_sim = True
    dont_move = True
    is_detect_dust = True

    # strat.arm.dsr_resume()

    # Set tool weight
    # strat.arm.dsr_emergency_stop()
    # rospy.sleep(1)
    # res = strat.arm.dsr_set_tool("Tool_clean")
    # rospy.loginfo("Tool weight set")

    # Wait for the mir system up
    # rospy.wait_for_message("/odom", Odometry)
    index_mir = 0
    for spot in strat.base_trajectory:
        # Debug
        # modif_spot = [[1.5406690835952759, -0.5502933263778687, 3.1929985444348996],
        #               [-0.6093308925628662 - 0.25, -0.4002932906150818, 6.123876490737688],
        #               [0.5906690955162048, 0.6497067213058472 + 0.25, 4.67862561105184],
        #               [0.5406690835952759, -1.8502932786941528 - 0.25, 1.6055759290465765]]
        # actual_spot = modif_spot[index_mir]
        # index_mir += 1
        # End debug

        print(spot[0], spot[1], spot[2])
        strat.arm.go_home()
        while strat.arm.check_motion() != 0:
            rospy.sleep(0.8)

        answ = input("Are you ready to go to the next spot ?")
        if answ == "no":
            pass
        if dont_move:
            result_mir = True
            spot_pose = Pose2D()
            spot_pose.x = spot[0]
            spot_pose.y = spot[1]
            spot_pose.theta = spot[2]
            strat.spot_pub.publish(spot_pose)
        else:
            if is_sim:
                result_mir, trans_machine = strat.robot.move_mobile_base(spot[0], spot[1], spot[2])
                result_mir = True
                # rospy.sleep(10)
                collision_stamp = PoseStamped()
                collision_stamp.header.frame_id = "machine"
                collision_stamp.pose.orientation.w = 1
                try:
                    trans_machine = tf_buffer.lookup_transform('world', "machine", rospy.Time(),
                                                              rospy.Duration(1.0))
                except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
                        tf2_ros.ExtrapolationException):
                    rospy.loginfo("pb dans la transformation")

                collision_stamp = tf2_geometry_msgs.do_transform_pose(collision_stamp, trans_machine)
                strat.arm.add_machine_colision(rospkg.RosPack().get_path('cleaning') + rospy.get_param("/machine_mesh"),
                                               collision_stamp)
                # rospy.sleep(10)
                print("continue")
            else:
                result_mir = strat.robot.move_base(spot[0], spot[1], spot[2])
        # result_mir = False
        if result_mir:
            input("The mir arrived, does the vacuum ready ?")
            # # clear la octomap

            # activate octomap
            strat.octo_pub.publish(True)

            strat.arm.set_tcp("vacuum_tcp")

            arm_poses = strat.offline_traj[tuple(spot)]
            print(type(arm_poses))
            print(strat.offline_traj)

            strat.arm.set_tcp("camera_base")
            # Go to guards
            if arm_poses is None:
                continue
            for index, pose in enumerate(arm_poses):
                # clear la octomap
                # strat.arm.clear_collisions()

                if debug:
                    fkin = strat.arm.fkin_moveit(pose, "camera_base").pose_stamped[0]

                    tcp_pose = fkin.pose

                    # send tf
                    static_transform_stamped = geometry_msgs.msg.TransformStamped()
                    static_transform_stamped.header.stamp = rospy.Time.now()
                    static_transform_stamped.header.frame_id = "world"
                    static_transform_stamped.child_frame_id = "guard"
                    static_transform_stamped.transform.translation.x = tcp_pose.position.x
                    static_transform_stamped.transform.translation.y = tcp_pose.position.y
                    static_transform_stamped.transform.translation.z = tcp_pose.position.z
                    static_transform_stamped.transform.rotation.x = tcp_pose.orientation.x
                    static_transform_stamped.transform.rotation.y = tcp_pose.orientation.y
                    static_transform_stamped.transform.rotation.z = tcp_pose.orientation.z
                    static_transform_stamped.transform.rotation.w = tcp_pose.orientation.w

                    broadcaster_guard.sendTransform(static_transform_stamped)
                    rospy.loginfo('{nodeName} : Position pour le GUARD'.format(nodeName=rospy.get_name()))
                    print(np.degrees(pose))
                    rospy.loginfo('{nodeName} : GUARD numero: '.format(nodeName=rospy.get_name()))
                    print(str(index)+"sur " + str(len(arm_poses)))

                res = strat.arm.go_to_j(pose)

                config = JointState()
                config.position = pose
                if res:
                    config.velocity = [10, 10, 10, 10, 10, 10]
                else:
                    config.velocity = [0, 0, 0, 0, 0, 0]
                config.header.stamp = rospy.get_rostime()

                strat.guard_pub.publish(config)

                while strat.arm.check_motion() != 0:
                    rospy.sleep(0.1)
                rospy.sleep(2)
                # input("next pose:")
                # GO TO DUST
                if is_detect_dust and res:
                    print("mouvement reach !")
                    # # All collisions are clear to remove the dust collisions
                    # strat.arm.clear_collisions()
                    # Set the TCP at the end of vacuum, and we add 5cm to set up an approche point.
                    # the rest will be executed by compliance
                    strat.arm.set_tcp("vacuum_safe_tcp")
                    strat.arm.dsr_set_tcp("vacuum")

                    # Detect Dust in vacuum_tcp frame
                    dust_poses = strat.dust.ask_dust_poses(strat.color_image, strat.depth_image)
                    # Filter points
                    # Compute the path thought dust clusters in vacuum_tcp frame
                    entry_points, dust_path = strat.dust.dust_path(dust_poses)
                    # On a les entry point de chaque cluster et le path de chaque cluster
                    # Donc on peut se deplacer a l'entry_point avec moveit et utiliser le reste avec dsr
                    # en recuperant les orientations du entry point final,
                    # cad celui qui a ete realisé en fct des obstacles.

                    #  Define the oriantation and position for the entry pose to vacuum the dust

                    tcp_pose = strat.arm.get_pose()
                    trans_tcp = strat.tf_tools.get_transform("world", "vacuum_tcp")
                    # try:
                    #     trans_tcp = tf_buffer.lookup_transform('vacuum_tcp', "world", rospy.Time(),
                    #                                            rospy.Duration(1))
                    # except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
                    #         tf2_ros.ExtrapolationException):
                    #     rospy.loginfo(
                    #         '{nodeName} : Aucun message de la transformation'.format(nodeName=rospy.get_name()))
                    tcp_pose_world = tf2_geometry_msgs.do_transform_pose(tcp_pose, trans_tcp)

                    trans_world = strat.tf_tools.get_transform("vacuum_tcp", "world")
                    # try:
                    #     trans_world = tf_buffer.lookup_transform('world', "vacuum_tcp", rospy.Time(),
                    #                                              rospy.Duration(1))
                    # except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
                    #         tf2_ros.ExtrapolationException):
                    #     rospy.loginfo(
                    #         '{nodeName} : Aucun message de la transformation'.format(nodeName=rospy.get_name()))

                    entry_point_goals = []
                    colors_array = []
                    # Def orien et pos pour chaque entry_points in the world
                    # (because pathplanning is always for world frame)
                    for dust_cluster in entry_points:
                        pose = tcp_pose_world
                        pose.pose.position.x = dust_cluster[0]
                        pose.pose.position.y = dust_cluster[1]
                        pose.pose.position.z = dust_cluster[2]

                        # Set color to blue meaning no tried (red is not accessible and green is accescible
                        colors_array.append([0, 0, 1])

                        goal_pose = tf2_geometry_msgs.do_transform_pose(pose, trans_world)
                        entry_point_goals.append(goal_pose)

                    dust_path_world = []
                    for dust_cluster in dust_path:
                        dust_cluster_wolrd = []
                        for dust in dust_cluster:
                            pose_dust = PoseStamped()
                            pose_dust.header.frame_id = "rgb_camera_link"
                            pose_dust.pose.position.x = dust[0]
                            pose_dust.pose.position.y = dust[1]
                            pose_dust.pose.position.z = dust[2]
                            dust_world_pose = tf2_geometry_msgs.do_transform_pose(pose_dust, trans_world)
                            dust_cluster_wolrd.append(dust_world_pose)
                        dust_path_world.append(dust_cluster_wolrd)


                    print("dust goal et colors")
                    print(entry_point_goals)
                    # print(colors_array)

                    display_marker_array(Marker.SPHERE, entry_point_goals, colors_array, "world")

                    # while strat.arm.check_motion() != 0:
                    #     rospy.sleep(0.1)
                    # On deplace le robot a chaque entry_point
                    for i, entry in enumerate(entry_point_goals):
                        # if debug:
                        #     # send tf
                        #     static_transform_stamped = geometry_msgs.msg.TransformStamped()
                        #     static_transform_stamped.header.stamp = rospy.Time.now()
                        #     static_transform_stamped.header.frame_id = "world"
                        #     static_transform_stamped.child_frame_id = "goal"
                        #     static_transform_stamped.transform.translation.x = entry.pose.position.x
                        #     static_transform_stamped.transform.translation.y = entry.pose.position.y
                        #     static_transform_stamped.transform.translation.z = entry.pose.position.z
                        #     static_transform_stamped.transform.rotation.x = entry.pose.orientation.x
                        #     static_transform_stamped.transform.rotation.y = entry.pose.orientation.y
                        #     static_transform_stamped.transform.rotation.z = entry.pose.orientation.z
                        #     static_transform_stamped.transform.rotation.w = entry.pose.orientation.w
                        #     broadcaster_guard.sendTransform(static_transform_stamped)

                        print(entry.pose)
                        # input("test_3:")
                        res = strat.arm.go_to_l(entry.pose)
                        while strat.arm.check_motion() != 0:
                            rospy.sleep(0.1)
                        # input("test_1 :")
                        if res:
                            # Get orientation of the current tcp pose in
                            tcp_pose = strat.arm.dsr_get_pose()
                            print("TCP Pose:")
                            print(tcp_pose)


                            # # Get the matrix 3x3 for the rotation from the quaternion
                            # matrix = R.from_quat([tcp_pose.pose.orientation.x, tcp_pose.pose.orientation.y,
                            #                       tcp_pose.pose.orientation.z, tcp_pose.pose.orientation.w])
                            # # Change the coordinate system
                            # orient = matrix.as_euler('zyz', degrees=False)


                            # print(tcp_pose)
                            # Go to contact with compliance:
                            # tcp = strat.arm.dsr_set_tcp("vacuum")

                            for index, dust in enumerate(dust_path_world[i]):
                                dust_pose = [dust.pose.position.x, dust.pose.position.y, dust.pose.position.z,
                                             tcp_pose[3], tcp_pose[4], tcp_pose[5]]
                                print(dust_pose)
                                input("test_2: ")
                                strat.arm.set_compliance([100, 100, 100, 200, 200, 200])
                                res = strat.arm.dsr_go_to_l(dust_pose)
                                while strat.arm.check_motion() != 0:
                                    rospy.sleep(0.1)


                        # Stop compliance
                        strat.arm.release_compliance()
                        # send dust goal to telemetrie
                        pose = PoseStamped()
                        pose.pose = dust.pose
                        pose.header.stamp = rospy.get_rostime()
                        # Real frame is "world"
                        if res:
                            pose.header.frame_id = "success"
                        else:
                            pose.header.frame_id = "fail"
                        strat.dust_pub.publish(pose)

                        # we go out and we release the compliance
                        rospy.loginfo('{nodeName} : Go linear backward'.format(nodeName=rospy.get_name()))
                        strat.arm.dsr_go_relatif([0, 0, -75, 0, 0, 0])
                        rospy.sleep(4)




                        # STOP GO TO DUST

            # deactivate octomap
            strat.octo_pub.publish(False)
            # clear la octomap
            # strat.arm.clear_collisions()
            strat.arm.clear_collisions()

    # input("Cleanning finish, press enter to continue:")
    strat.finish_pub.publish(True)
    strat.arm.go_home()

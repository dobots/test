#!/usr/bin/env python3
# Copyright (c) 2020 The Plankton Authors.
# All rights reserved.
#
# This source code is derived from UUV Simulator
# (https://github.com/uuvsimulator/uuv_simulator)
# Copyright (c) 2016-2019 The UUV Simulator Authors
# licensed under the Apache license, Version 2.0
# cf. 3rd-party-licenses.txt file in the root directory of this source tree.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import threading
import traceback

import rclpy
from uuv_gazebo_ros_plugins_msgs.srv import SetThrusterState
from plankton_utils.time import time_in_float_sec
from plankton_utils.time import is_sim_time


def build_service_name(ns, thruster_id, service_name) -> str :
    return '/%s/thrusters/id_%d/%s' % (ns, thruster_id, service_name)

#==============================================================================
def main():
    rclpy.init()

    sim_time_param = is_sim_time()

    node = rclpy.create_node(
        'set_thrusters_states',
        allow_undeclared_parameters=True, 
        automatically_declare_parameters_from_overrides=True,
        parameter_overrides=[sim_time_param])

    node.get_logger().info('Set the state of thrusters for vehicle, namespace=' + node.get_namespace())

    thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    thread.start()

    # Make sure the clock has been updated when using sim time
    while node.get_clock().now() == rclpy.time.Time(clock_type=node.get_clock().clock_type):
        pass

    starting_time = 0.0
    if node.has_parameter('starting_time'):
        starting_time = node.get_parameter('starting_time').value
    if starting_time < 0:
        starting_time = time_in_float_sec(node.get_clock().now())

    node.get_logger().info('Starting time={} s'.format(starting_time))

    duration = 0.0
    if node.has_parameter('duration'):
        duration = node.get_parameter('duration').value

    if duration == 0.0:
        raise RuntimeError('Duration not set, leaving node...')

    node.get_logger().info('Duration [s]=%s' % ('Inf.' if duration < 0 else str(duration)))

    if node.has_parameter('is_on'):
        is_on = bool(node.get_parameter('is_on').get_parameter_value().bool_value)
    else:
        raise RuntimeError('is_on state flag not provided')

    thruster_id = -1
    if node.has_parameter('thruster_id'):
        if node.get_parameter('thruster_id').type_ == rclpy.Parameter.Type.INTEGER:
            thruster_id = node.get_parameter('thruster_id').get_parameter_value().integer_value
    else:
        raise RuntimeError('Thruster ID not given')

    if thruster_id < 0:
        raise RuntimeError('Invalid thruster ID')

    node.get_logger().info('Setting state of thruster #{} as {}'.format(thruster_id, 'ON' if is_on else 'OFF'))

    vehicle_name = node.get_namespace().replace('/', '')

    srv_name = build_service_name(vehicle_name, thruster_id, 'set_thruster_state')

    try:
        set_state = node.create_client(SetThrusterState, srv_name)
    except Exception as e:
        raise RuntimeError('Service call failed, error=' + str(e))

    if not set_state.wait_for_service(timeout_sec=2):
        raise RuntimeError('Service %s not available! Closing node...' %(srv_name))

    FREQ = 100
    rate = node.create_rate(FREQ)

    while time_in_float_sec(node.get_clock().now()) < starting_time:
        # Just a guard for really short timeouts
        if 1.0 / FREQ < starting_time: 
            rate.sleep()

    # First request
    req = SetThrusterState.Request()
    req.on = is_on

    future = set_state.call_async(req)

    # NB : spining is done from another thread   
    while not future.done():
        pass

    try:
        response = future.result()
    except Exception as e:
        node.get_logger().error('Service call ' + srv_name + ' failed, error=' + repr(e))
    else:
        if response.success:
            node.get_logger().info('Time={} s'.format(time_in_float_sec(node.get_clock().now())))
            node.get_logger().info('Current state of thruster #{}={}'.format(thruster_id, 'ON' if is_on else 'OFF'))
        else:
            node.get_logger().error('Service call ' + srv_name + ' returned a "failed" value')

    # Returning to previous state
    if duration > 0:
        while time_in_float_sec(node.get_clock().now()) < starting_time + duration:
            if 1.0 / FREQ < starting_time + duration:
                rate.sleep()

        req.on = not is_on
        success = set_state.call(req)

        while not future.done():
            pass

        try:
            response = future.result()
        except Exception as e:
            node.get_logger().error('Service call ' + srv_name + ' failed, error=' + str(e))
        else:
            if response.success:
                node.get_logger().info('Time={} s'.format(time_in_float_sec(node.get_clock().now())))
                node.get_logger().info('Returning to previous state of thruster #{}={}'.format(thruster_id, 'ON' if not is_on else 'OFF'))
            else:
                node.get_logger().error('Service call ' + srv_name + ' returned a "failed" value')

    node.get_logger().info('Leaving node...')

    node.destroy_node()
    rclpy.shutdown()
    thread.join()


# =============================================================================
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Something went wrong: ' + repr(e))
        print(traceback.print_exc())

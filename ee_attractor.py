

import math
import numpy as np
from isaacgym import gymapi
from isaacgym import gymutil



def deg2rad_joint_angles(deg_list):

    rad_list = [np.radians(deg_list[i]) for i in range(len(deg_list))]

    return rad_list


ur3_default_dof_pos = deg2rad_joint_angles([5.55, -71.55, -108.25, -3.83, 84.09, -0.0019])        # self.ur3_default_dof_pos = to_torch([-0.2, -1.2, 0, -2.2, 0, 2.7, 0], device=self.device) # right

# Initialize gym
gym = gymapi.acquire_gym()

# Parse arguments
args = gymutil.parse_arguments(description="Fran Attractor Example")

# configure sim
sim_params = gymapi.SimParams()
sim_params.dt = 1.0 / 60.0
sim_params.up_axis = gymapi.UP_AXIS_Z
sim_params.substeps = 2

if args.physics_engine == gymapi.SIM_FLEX:
    sim_params.flex.solver_type = 5
    sim_params.flex.num_outer_iterations = 4
    sim_params.flex.num_inner_iterations = 15
    sim_params.flex.relaxation = 0.75
    sim_params.flex.warm_start = 0.8
elif args.physics_engine == gymapi.SIM_PHYSX:
    sim_params.physx.solver_type = 1
    sim_params.physx.num_position_iterations = 4
    sim_params.physx.num_velocity_iterations = 1
    sim_params.physx.num_threads = args.num_threads
    sim_params.physx.use_gpu = args.use_gpu

sim_params.use_gpu_pipeline = False
if args.use_gpu_pipeline:
    print("WARNING: Forcing CPU pipeline.")

sim = gym.create_sim(args.compute_device_id, args.graphics_device_id, args.physics_engine, sim_params)

if sim is None:
    print("*** Failed to create sim")
    quit()

# Create viewer
viewer = gym.create_viewer(sim, gymapi.CameraProperties())
if viewer is None:
    print("*** Failed to create viewer")
    quit()

# Add ground plane
plane_params = gymapi.PlaneParams()
plane_params.normal = gymapi.Vec3(0, 0, 1) # z up
gym.add_ground(sim, plane_params)

# Load franka asset
asset_root = "./assets"
franka_asset_file = "urdf/door_test/hook_test.urdf"

asset_options = gymapi.AssetOptions()
asset_options.fix_base_link = True
asset_options.flip_visual_attachments = True
asset_options.armature = 0.01
asset_options.disable_gravity = True

print("Loading asset '%s' from '%s'" % (franka_asset_file, asset_root))
franka_asset = gym.load_asset(
    sim, asset_root, franka_asset_file, asset_options)

# Set up the env grid
num_envs = 100
spacing = 1.0
env_lower = gymapi.Vec3(-spacing, 0.0, -spacing)
env_upper = gymapi.Vec3(spacing, spacing, spacing)

# Some common handles for later use
envs = []
franka_handles = []
franka_hand = "hand_base"

# Attractor setup
attractor_handles = []
attractor_properties = gymapi.AttractorProperties()
attractor_properties.stiffness = 5e5
attractor_properties.damping = 5e3
##############################################
attractor_properties.stiffness = 5e5
attractor_properties.damping = 0.0
##############################################

# Make attractor in all axes
attractor_properties.axes = gymapi.AXIS_ALL
pose = gymapi.Transform()
pose.p = gymapi.Vec3(0, 0.0, 0.5)
pose.r = gymapi.Quat(0, 0, 0, 1)

# Create helper geometry used for visualization
# Create an wireframe axis
axes_geom = gymutil.AxesGeometry(0.5)
# Create an wireframe sphere
sphere_rot = gymapi.Quat.from_euler_zyx(0.5 * math.pi, 0, 0)
sphere_pose = gymapi.Transform(r=sphere_rot)
sphere_geom = gymutil.WireframeSphereGeometry(0.03, 12, 12, sphere_pose, color=(1, 0, 0))

print("Creating %d environments" % num_envs)
num_per_row = int(math.sqrt(num_envs))

for i in range(num_envs):
    # create env
    env = gym.create_env(sim, env_lower, env_upper, num_per_row)
    envs.append(env)

    # add franka
    franka_handle = gym.create_actor(env, franka_asset, pose, "hook", i, 2)
    body_dict = gym.get_actor_rigid_body_dict(env, franka_handle)
    props = gym.get_actor_rigid_body_states(env, franka_handle, gymapi.STATE_POS)
    hand_handle = body = gym.find_actor_rigid_body_handle(env, franka_handle, franka_hand)
    # print('hand_handle', hand_handle) 

    # Initialize the attractor
    attractor_properties.target = props['pose'][:][body_dict[franka_hand]]
    # attractor_properties.target.p.y -= 0.1 #これ何？
    # attractor_properties.target.p.z = 0.1 # これ何？ただ値いじってるだけ？
    attractor_properties.rigid_handle = hand_handle

    # Draw axes and sphere at attractor location
    gymutil.draw_lines(axes_geom, gym, viewer, env, attractor_properties.target)
    gymutil.draw_lines(sphere_geom, gym, viewer, env, attractor_properties.target)

    franka_handles.append(franka_handle)
    attractor_handle = gym.create_rigid_body_attractor(env, attractor_properties)
    attractor_handles.append(attractor_handle)

# get joint limits and ranges for Franka
franka_dof_props = gym.get_actor_dof_properties(envs[0], franka_handles[0])
franka_lower_limits = franka_dof_props['lower']
franka_upper_limits = franka_dof_props['upper']
franka_ranges = franka_upper_limits - franka_lower_limits
franka_mids = 0.5 * (franka_upper_limits + franka_lower_limits)
franka_num_dofs = len(franka_dof_props)
print('franka num_dof', franka_num_dofs)

# override default stiffness and damping values
franka_dof_props['stiffness'].fill(1000.0)
franka_dof_props['damping'].fill(1000.0)

# Give a desired pose for first 2 robot joints to improve stability
franka_dof_props["driveMode"][0:2] = gymapi.DOF_MODE_POS

franka_dof_props["driveMode"][7:] = gymapi.DOF_MODE_POS
franka_dof_props['stiffness'][7:] = 1e10
franka_dof_props['damping'][7:] = 1e5

for i in range(num_envs):
    gym.set_actor_dof_properties(envs[i], franka_handles[i], franka_dof_props)


def update_franka(t):
    gym.clear_lines(viewer)
    for i in range(num_envs):
        # Update attractor target from current franka state
        attractor_properties = gym.get_attractor_properties(envs[i], attractor_handles[i])
        pose = attractor_properties.target
        # print(pose)
        pose.p.x = 0.2 * math.sin(1.5 * t - math.pi * float(i) / num_envs)
        pose.p.y = 0.2 * math.cos(2.5 * t - math.pi * float(i) / num_envs)
        pose.p.z = 0.5 + 0.2 * math.cos(1.5 * t - math.pi * float(i) / num_envs)

        # pose.p.x = 0.0
        # pose.p.y = 0.2
        # pose.p.z = 0.8

        # gym.set_attractor_target(envs[i], attractor_handles[i], pose)
        # print(pose.r.x)
        rot_euler = list(gymapi.Quat.to_euler_zyx(pose.r))
        # rot_euler[2] += 0.02
        rot_euler[1] += 0.02
        rot_euler[0] += 0.02
        pose.r = gymapi.Quat.from_euler_zyx(*rot_euler)
        # print(rot_euler)
        gym.set_attractor_target(envs[i], attractor_handles[i], pose)

        # Draw axes and sphere at attractor location
        gymutil.draw_lines(axes_geom, gym, viewer, envs[i], pose)
        gymutil.draw_lines(sphere_geom, gym, viewer, envs[i], pose)


for i in range(num_envs):
    # Set updated stiffness and damping properties
    gym.set_actor_dof_properties(envs[i], franka_handles[i], franka_dof_props)

    # Set ranka pose so that each joint is in the middle of its actuation range
    franka_dof_states = gym.get_actor_dof_states(envs[i], franka_handles[i], gymapi.STATE_NONE)
    for j in range(franka_num_dofs):
        franka_dof_states['pos'][j] = franka_mids[j]
    gym.set_actor_dof_states(envs[i], franka_handles[i], franka_dof_states, gymapi.STATE_POS)

# Point camera at environments
cam_pos = gymapi.Vec3(1.0, 1.0, 1.5)
cam_target = gymapi.Vec3(0.5, 0.0, 0.7)
gym.viewer_camera_look_at(viewer, None, cam_pos, cam_target)

# Time to wait in seconds before moving robot
next_franka_update_time = 1.5

while not gym.query_viewer_has_closed(viewer):
    # Every 0.01 seconds the pose of the attactor is updated
    t = gym.get_sim_time(sim)
    if t >= next_franka_update_time:
        update_franka(t)
        next_franka_update_time += 0.01

    # Step the physics
    gym.simulate(sim)
    gym.fetch_results(sim, True)

    # Step rendering
    gym.step_graphics(sim)
    gym.draw_viewer(viewer, sim, False)
    gym.sync_frame_time(sim)

print("Done")

gym.destroy_viewer(viewer)
gym.destroy_sim(sim)
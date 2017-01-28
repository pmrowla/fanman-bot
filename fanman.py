#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fanmanager Discord bot."""

import argparse
import logging
import sys

import discord
from discord.ext import commands

import yaml

# Default bot configuration, see README and config.yml.example for more information
config = {
    'token': 'token',
    'logfile': 'discord-fanman.log',
    'bias_roles': [],
    'general_channel': '#general',
    'updates_channel': '#updates',
    'join_message': None,
    'part_message': None,
}

logger = logging.getLogger('discord-fanman')
logger.setLevel(logging.INFO)
stderr_handler = logging.StreamHandler()
stderr_handler.setLevel(logging.WARNING)
stderr_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(stderr_handler)

description = 'Fanmanager Discord bot.'
bot = commands.Bot(command_prefix='.', description=description)
general_channels = {}
updates_channels = {}
bias_roles = {}


def configure(config_file, debug=False):
    """Configure the bot."""
    try:
        f = open(config_file, 'r')
        loaded_config = yaml.load(open(config_file, 'r'))
        f.close()
        config.update(loaded_config)
        if not isinstance(loaded_config, dict):
            loaded_config = {}
    except FileNotFoundError:
        loaded_config = {}
    except (yaml.parser.ParserError, ValueError):
        logger.error('Invalid configuration file: {}, using default values.'.format(config_file))
    formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    file_handler = logging.FileHandler(filename=config.get('logfile'))
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if debug:
        logger.setLevel(logging.DEBUG)
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)
    if not isinstance(config['bias_roles'], list):
        config['bias_roles'] = [config['bias_roles']]


def get_role(obj, role_name):
    """Return a Role if the specified object has the specified role."""
    for role in obj.roles:
        if role.name == role_name:
            return role
    return None


@bot.event
async def on_ready():
    """Handle on_ready event."""
    logger.info('Logged in as {} ({})'.format(bot.user.name, bot.user.id))
    for server in bot.servers:
        general = config.get('general_channel').lstrip('#')
        updates = config.get('updates_channel').lstrip('#')
        for channel in server.channels:
            if channel.type == discord.ChannelType.text:
                if str(channel) == general:
                    general_channels[server] = channel
                if str(channel) == updates:
                    updates_channels[server] = channel
        config_roles = [i.lower() for i in config['bias_roles']]
        bias_roles[server] = {}
        for role_name in config_roles:
            (bias, sub) = (role_name.capitalize(), role_name.lower())
            bias_role = get_role(server, bias)
            if not bias_role:
                await bot.create_role(server, name=bias, hoist=True)
                bias_role = get_role(server, bias)
            sub_role = get_role(server, sub)
            if not sub_role:
                await bot.create_role(server, name=sub)
                sub_role = get_role(server, sub)
            bias_roles[server][sub] = (bias_role, sub_role)


@bot.event
async def on_channel_delete(channel):
    """Handle channel delete event."""
    if channel.type == discord.ChannelType.text:
        for i in [general_channels, updates_channels]:
            if channel.server in i:
                for s, c in i.items():
                    if channel == c:
                        del i[s]


@bot.event
async def on_channel_create(channel):
    """Handle channel create event."""
    if channel.type == discord.ChannelType.text:
        general = config.get('general_channel').lstrip('#')
        updates = config.get('updates_channel').lstrip('#')
        if str(channel) == general:
            general_channels[channel.server] = channel
        if str(channel) == updates:
            updates_channels[channel.server] = channel


@bot.event
async def on_member_join(member):
    """Handle member join event."""
    msg = config.get('join_message')
    channel = general_channels.get(member.server)
    if msg and channel:
        logger.debug('Member {} joined server {}'.format(member, member.server))
        await bot.send_message(channel, msg.format(user=member.mention))


@bot.event
async def on_member_remove(member):
    """Handle member part event."""
    msg = config.get('part_message')
    channel = general_channels.get(member.server)
    if msg and channel:
        logger.debug('Member {} left server {}'.format(member, member.server))
        await bot.send_message(channel, msg.format(user=member.mention))


def _get_bias(member):
    for (bias, sub) in bias_roles[member.server].values():
        if bias in member.roles:
            return bias
    return None


@bot.command(pass_context=True)
async def bias(ctx, role_name: str):
    server = ctx.message.server
    role_name = role_name.lower()
    if server in bias_roles:
        member = ctx.message.author
        (bias, sub) = bias_roles[member.server].get(role_name, (None, None))
        if not bias:
            return
        old_bias = _get_bias(member)
        if bias == old_bias:
            await bot.say('{} bias is already {}.'.format(role_name.capitalize()))
        else:
            if old_bias:
                roles = member.roles
                roles.remove(old_bias)
                roles.append(bias)
                logger.debug('Replacing role {} with {} for member {}'.format(old_bias, bias, member))
                await bot.replace_roles(member, *roles)
                await bot.say('{} changed bias from {} to {}.'.format(member.mention, old_bias.name.lower(), role_name))
            else:
                logger.debug('Adding role {} to member {}'.format(bias, member))
                await bot.add_roles(member, bias)
                await bot.say('{} set bias to {}.'.format(member.mention, role_name.capitalize()))


@bot.command(pass_context=True)
async def sbias(ctx, role_name: str):
    server = ctx.message.server
    role_name = role_name.lower()
    if server in bias_roles:
        member = ctx.message.author
        (bias, sub) = bias_roles[member.server].get(role_name, (None, None))
        if not sub:
            return
        if sub in member.roles:
            await bot.say('{} already has sub-bias {}.'.format(member.mention, role_name.capitalize()))
        else:
            logger.debug('Adding role {} to member {}'.format(sub, member))
            await bot.add_roles(member, sub)
            await bot.say('{} set sub-bias to {}.'.format(member.mention, role_name.capitalize()))


@bot.command(pass_context=True)
async def unbias(ctx):
    server = ctx.message.server
    if server in bias_roles:
        member = ctx.message.author
        bias = _get_bias(member)
        if bias in member.roles:
            logger.debug('Removing role {} from member {}'.format(bias, member))
            await bot.remove_roles(member, bias)
            await bot.say('{} removed {} bias.'.format(member.mention, bias.name))
        else:
            await bot.say('{} you do not have a bias set.'.format(member.mention))


@bot.command(pass_context=True)
async def unsbias(ctx, role_name: str):
    server = ctx.message.server
    if server in bias_roles:
        member = ctx.message.author
        (bias, sub) = bias_roles[member.server].get(role_name, (None, None))
        if not sub:
            return
        if sub in member.roles:
            logger.debug('Removing role {} from member {}'.format(sub, member))
            await bot.remove_roles(member, sub)
            await bot.say('{} removed {} sub-bias.'.format(member.mention, role_name.capitalize()))
        else:
            await bot.say('{} you do not have a sub-bias {}.'.format(member.mention, role_name.capitalize()))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-c', '--config-file', nargs=1, dest='config_file', default='config.yml',
                        help='Configuration file, defaults to config.yml')
    parser.add_argument('-d', '--debug', action='store_true')
    args = parser.parse_args()
    configure(args.config_file, debug=args.debug)
    bot.run(config.get('token'))


if __name__ == '__main__':
    main()

from aiogram import Router, F
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram.types import Message
from sqlalchemy import select
from database.models import User, Setting, Pair
from datetime import datetime
from bot import get_users_ready_for_matching
from random import shuffle

admin_router = Router()

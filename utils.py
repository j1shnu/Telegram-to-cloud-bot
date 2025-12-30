import os
import shutil
import asyncio

async def ensure_upload_dir(path):
    if not os.path.exists(path):
        await asyncio.to_thread(os.makedirs, path)

async def get_files(path):
    if not os.path.exists(path):
        return []
    return await asyncio.to_thread(sorted, os.listdir(path))

async def delete_file(path):
    if os.path.exists(path):
        if os.path.isfile(path):
            await asyncio.to_thread(os.remove, path)
        elif os.path.isdir(path):
            await asyncio.to_thread(shutil.rmtree, path)
        return True
    return False

async def get_file_size(path):
    if os.path.exists(path):
        return await asyncio.to_thread(os.path.getsize, path)
    return 0

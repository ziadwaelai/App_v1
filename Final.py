import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from zipfile import ZipFile
from PIL import Image, UnidentifiedImageError
import re
from transformers import pipeline


# Function to convert Google Drive link to direct download link
def convert_drive_link(link):
    match = re.search(r'/d/([^/]+)', link)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return link

# Function to download an image from a URL
def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    return None

# Function to resize image to a specific size
def resize_image(image_content, size=(1024, 1024)):
    try:
        image = Image.open(BytesIO(image_content))
        image = image.resize(size)
        if image.mode == 'RGBA':
            image = image.convert('RGB')
        img_byte_arr = BytesIO()
        image.save(img_byte_arr, format='JPEG')
        return img_byte_arr.getvalue()
    except UnidentifiedImageError:
        return None

# Function to remove background from an image
def remove_background(image_content):
    try:
        image = Image.open(BytesIO(image_content))
        pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
        output_img = pipe(image)
        img_byte_arr = BytesIO()
        output_img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
    except UnidentifiedImageError:
        return None

# Function to combine the foreground image with a background image
def combine_with_background(foreground_content, background_content, resize_foreground=False):
    try:
        foreground = Image.open(BytesIO(foreground_content)).convert("RGBA")
        background = Image.open(BytesIO(background_content)).convert("RGBA")
        background = background.resize((1024, 1024))

        if resize_foreground:
            # Calculate the scaling factor to cover 70% of the background
            fg_area = foreground.width * foreground.height
            bg_area = background.width * background.height
            scale_factor = (0.8 * bg_area / fg_area) ** 0.5

            new_width = int(foreground.width * scale_factor)
            new_height = int(foreground.height * scale_factor)

            foreground = foreground.resize((new_width, new_height))

            # Save the dimensions of the object
            dimensions = (new_width, new_height)
        else:
            dimensions = (foreground.width, foreground.height)

        # Center the foreground on the background
        fg_width, fg_height = foreground.size
        bg_width, bg_height = background.size
        position = ((bg_width - fg_width) // 2, (bg_height - fg_height) // 2)

        combined = background.copy()
        combined.paste(foreground, position, foreground)
        img_byte_arr = BytesIO()
        combined.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue(), dimensions
    except UnidentifiedImageError:
        return None, None

# Function to download all images as a ZIP file
def download_all_images_as_zip(images_info, remove_bg=False, add_bg=False, bg_image=None, resize_foreground=False):
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, 'w') as zf:
        for name, url_or_file in images_info:
            if isinstance(url_or_file, str):
                url = convert_drive_link(url_or_file)
                image_content = download_image(url)
            else:
                image_content = url_or_file.read()

            if image_content:
                if remove_bg:
                    processed_image = remove_background(image_content)
                    ext = 'png'
                else:
                    processed_image = resize_image(image_content)
                    ext = 'png'

                if add_bg and bg_image:
                    processed_image, dimensions = combine_with_background(processed_image, bg_image, resize_foreground=resize_foreground)
                    ext = 'png'

                if processed_image:
                    zf.writestr(f"{name}", processed_image)
    zip_buffer.seek(0)
    return zip_buffer

# Streamlit UI
#css upload file
st.markdown("""
    <style>
    .st-emotion-cache-1erivf3,.st-emotion-cache-1gulkj5 {
       display: flex;
       -webkit-box-align: center;
       align-items: center;
       flex-direction: column;
       justify-content: space-around;
       height: 175px;

       }

    </style>
    """, unsafe_allow_html=True)

# st.set_page_config(
#     page_title="PhotoMaster",
#     page_icon="🖼️"
# )


# ---------- HEADER ----------
st.title("🖼️ PhotoMaster")

# Page layout
col1, col2 = st.columns([2, 1])

with col1:
    # st.markdown("<div  width='200' height='200'>upload</div>")
    # st.markdown("")
    # Set page title and layout
#st.set_page_config(page_title="Shobbak Tool", layout="wide")

# Custom CSS to style the buttons and other elements
# st.markdown("""
#     <style>
#     .st-emotion-cache-1erivf3 {
#        display: flex;
#        -webkit-box-align: center;
#        align-items: center;
#        flex-direction: column;
#        justify-content: space-around;
#        height: 150px;

#        }

#     </style>
#     """, unsafe_allow_html=True)

    #uploaded_files = st.file_uploader("Upload an Excel file (xlsx/csv) or images (jpg/jpeg/png)", type=["xlsx", "csv", "jpg", "jpeg", "png"], accept_multiple_files=True)
    uploaded_files = st.file_uploader("",type=["xlsx", "csv", "jpg", "jpeg", "png"], accept_multiple_files=True)
with col2:
    st.markdown("")
    remove_bg = st.checkbox("Remove background")
    add_bg = st.checkbox("Add background")
    resize_fg = st.checkbox("Resize")
    st.checkbox("Compress and Convert Format")
images_info = []
if uploaded_files:
    if len(uploaded_files) == 1 and uploaded_files[0].name.endswith(('.xlsx', '.csv')):
        file_type = 'excel'
    elif all(file.type.startswith('image/') for file in uploaded_files):
        file_type = 'images'
    else:
        file_type = 'mixed'

    if file_type == 'mixed':
        st.error("You should work with one type of file: either an Excel file or images.")
    else:
        if file_type == 'excel':
            uploaded_file = uploaded_files[0]
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)

            if 'links' in df.columns and ('name' in df.columns or 'names' in df.columns):
                df.dropna(subset=['links'], inplace=True)
                images_info = list(zip(df['name'], df['links']))
            else:
                st.error("The uploaded file must contain 'links' and 'name' columns.")

        elif file_type == 'images':
            images_info = [(file.name, file) for file in uploaded_files]

if images_info:
    bg_image = None
    if add_bg:
        bg_file = st.file_uploader("Upload background image", type=["jpg", "jpeg", "png"])
        if bg_file:
            bg_image = resize_image(bg_file.read())

    st.markdown("## Preview")
    if st.button("Download All Images", key="download_all"):
        zip_buffer = download_all_images_as_zip(images_info, remove_bg=remove_bg, add_bg=add_bg, bg_image=bg_image, resize_foreground=resize_fg)
        st.download_button(
            label="Download All Images as ZIP",
            data=zip_buffer,
            file_name="all_images.zip",
            mime="application/zip"
        )

    cols = st.columns(2)
    for i, (name, url_or_file) in enumerate(images_info):
        col = cols[i % 2]
        with col:
            if isinstance(url_or_file, str):
                url = convert_drive_link(url_or_file)
                image_content = download_image(url)
            else:
                image_content = url_or_file.read()

            if image_content:
                if remove_bg:
                    processed_image = remove_background(image_content)
                    ext = 'png'
                else:
                    processed_image = resize_image(image_content)
                    ext = 'png'

                if add_bg and bg_image:
                    processed_image, dimensions = combine_with_background(processed_image, bg_image, resize_foreground=resize_fg)
                    ext = 'png'

                if processed_image:
                    st.image(processed_image, caption=name)
                    st.download_button(
                        label=f"Download {name.rsplit('.', 1)[0]}",
                        data=processed_image,
                        file_name=f"{name.rsplit('.', 1)[0]}.{ext}",
                        mime=f"image/{ext}"
                    )

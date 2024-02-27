from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from .forms import *
from django.http import Http404
from .models import Movie, Myrating, MyList
from django.db.models import Q
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.db.models import Case, When
import pandas as pd
import matplotlib.pyplot as plt
import os
import csv
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import numpy as np
from wordcloud import WordCloud

# Create your views here.

def index(request):
    movies_list = Movie.objects.all()
    paginator = Paginator(movies_list, 8)  # Show 8 movies per page

    page = request.GET.get('page')
    try:
        movies = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        movies = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        movies = paginator.page(paginator.num_pages)

    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/list.html', {'movies': movies})

    # Check if there is any data before rendering pagination
    if movies_list.exists():
        return render(request, 'recommend/list.html', {'movies': movies, 'paginator': paginator})

    return render(request, 'recommend/list.html', {'movies': movies})

# Show details of the movie
def detail(request, movie_id):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404
    movies = get_object_or_404(Movie, id=movie_id)
    movie = Movie.objects.get(id=movie_id)
    
    temp = list(MyList.objects.all().values().filter(movie_id=movie_id,user=request.user))
    if temp:
        update = temp[0]['watch']
    else:
        update = False
    if request.method == "POST":

        # For my list
        if 'watch' in request.POST:
            watch_flag = request.POST['watch']
            if watch_flag == 'on':
                update = True
            else:
                update = False
            if MyList.objects.all().values().filter(movie_id=movie_id,user=request.user):
                MyList.objects.all().values().filter(movie_id=movie_id,user=request.user).update(watch=update)
            else:
                q=MyList(user=request.user,movie=movie,watch=update)
                q.save()
            if update:
                messages.success(request, "Movie added to your list!")
            else:
                messages.success(request, "Movie removed from your list!")

            
        # For rating
        else:
            rate = request.POST['rating']
            if Myrating.objects.all().values().filter(movie_id=movie_id,user=request.user):
                Myrating.objects.all().values().filter(movie_id=movie_id,user=request.user).update(rating=rate)
            else:
                q=Myrating(user=request.user,movie=movie,rating=rate)
                q.save()

            messages.success(request, "Rating has been submitted!")

        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    out = list(Myrating.objects.filter(user=request.user.id).values())

    # To display ratings in the movie detail page
    movie_rating = 0
    rate_flag = False
    for each in out:
        if each['movie_id'] == movie_id:
            movie_rating = each['rating']
            rate_flag = True
            break

    context = {'movies': movies,'movie_rating':movie_rating,'rate_flag':rate_flag,'update':update}
    return render(request, 'recommend/detail.html', context)


# MyList functionality
def watch(request):

    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movies = Movie.objects.filter(mylist__watch=True,mylist__user=request.user)
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/watch.html', {'movies': movies})

    return render(request, 'recommend/watch.html', {'movies': movies})


# To get similar movies based on user rating
def get_similar(movie_name,rating,corrMatrix):
    similar_ratings = corrMatrix[movie_name]*(rating-2.5)
    similar_ratings = similar_ratings.sort_values(ascending=False)
    return similar_ratings

# Recommendation Algorithm
def recommend(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movie_rating = pd.DataFrame(list(Myrating.objects.all().values()))

    # Check if the DataFrame is not empty
    if not movie_rating.empty:
        print(movie_rating.columns)

        new_user = movie_rating['user_id'].nunique()  # Use 'user_id' instead of 'user'
        current_user_id = request.user.id

        # if new user not rated any movie
        if current_user_id > new_user:
            movie = Movie.objects.get(id=19)
            q = Myrating(user=request.user, movie=movie, rating=0)
            q.save()

        userRatings = movie_rating.pivot_table(index=['user_id'], columns=['movie_id'], values='rating')
        userRatings = userRatings.fillna(0, axis=1)
        corrMatrix = userRatings.corr(method='pearson')

        user = pd.DataFrame(list(Myrating.objects.filter(user=request.user).values())).drop(['user_id', 'id'], axis=1)
        user_filtered = [tuple(x) for x in user.values]
        movie_id_watched = [each[0] for each in user_filtered]

        similar_movies = pd.DataFrame()
        for movie, rating in user_filtered:
            similar_ratings = get_similar(movie, rating, corrMatrix)
            similar_movies = pd.concat([similar_movies, similar_ratings], axis=1)

        # Print the similarity matrix
        print("Pearson Correlation Matrix:")
        print(corrMatrix)

        # Sum along columns to get total similarity for each movie
        total_similarity = similar_movies.sum(axis=1)

        # Print the total similarity for each movie
        print("Total Similarity for Each Movie:")
        print(total_similarity)

        # Get the movies not watched by the user
        movies_id_recommend = [movie_id for movie_id in total_similarity.index if movie_id not in movie_id_watched]

        # Sort movies by total similarity and get top recommendations
        movies_id_recommend = sorted(movies_id_recommend, key=lambda x: total_similarity[x], reverse=True)[:10]

        # Print the top recommended movie IDs
        print("Top Recommended Movie IDs:")
        print(movies_id_recommend)

        # Retrieve movie objects based on recommendations
        preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(movies_id_recommend)])
        movie_list = list(Movie.objects.filter(id__in=movies_id_recommend).order_by(preserved))

        # Create a list to store recommended movie information
        recommended_movies_info = []

        # Iterate through recommended movies and gather their information
        for movie in movie_list:
            try:
                rating_obj = Myrating.objects.get(user=request.user, movie=movie)
                rating = rating_obj.rating
            except Myrating.DoesNotExist:
                rating = float('nan')  # Rating not given by the user
            
            movie_info = {
                'Title': movie.title,
                'Genre': movie.genre,
                'Rating': rating
            }
            recommended_movies_info.append(movie_info)

        # Convert the list of dictionaries to a DataFrame
        recommended_movies_df = pd.DataFrame(recommended_movies_info)

        # Define the path for saving the CSV file in the same directory as your Django project file
        csv_file_path = os.path.join(os.path.dirname(__file__), f'{request.user.username}_recommended_movies.csv')

        # Write the DataFrame to a CSV file
        recommended_movies_df.to_csv(csv_file_path, index=False)

        # Get the movies watched by the user
        watched_movies = MyList.objects.filter(user=request.user, watch=True).values_list('movie_id', flat=True)

        # Count the number of correct recommendations
        correct_recommendations = sum(movie.id in watched_movies for movie in movie_list)

        # Calculate accuracy
        total_recommendations = len(movies_id_recommend)
        accuracy = correct_recommendations / total_recommendations if total_recommendations > 0 else 0.0
        # Create a bar chart for accuracy visualization
        plt.figure(figsize=(6, 4))
        plt.bar(['Accuracy'], [accuracy], color='skyblue')
        plt.ylabel('Accuracy')
        plt.ylim(0, 1)  # Set y-axis limits between 0 and 1
        plt.title('Accuracy of Recommendations')
        plt.tight_layout()

        # Define the path for saving the image file in the same directory as your Django project file
        image_file_path = os.path.join(os.path.dirname(__file__), f'{request.user.username}_accuracy_chart.png')

        # Save the bar chart as an image file
        plt.savefig(image_file_path)

        # Close the plot to release memory
        plt.close()

        # Calculate the distribution of genres among recommended movies
        genre_counts = recommended_movies_df['Genre'].value_counts()

        # Plot a pie chart to visualize the genre distribution
        plt.figure(figsize=(8, 6))
        plt.pie(genre_counts, labels=genre_counts.index, autopct='%1.1f%%', startangle=140)
        plt.title('Genre Distribution of Recommended Movies')
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        plt.tight_layout()

        # Define the path for saving the pie chart image file
        pie_chart_file_path = os.path.join(os.path.dirname(__file__), f'{request.user.username}_genre_distribution_pie_chart.png')

        # Save the pie chart as an image file
        plt.savefig(pie_chart_file_path)

        # Close the plot to release memory
        plt.close()

        # Plot a bar chart to visualize the genre distribution
        plt.figure(figsize=(8, 6))
        genre_counts.plot(kind='bar', color='skyblue')
        plt.xlabel('Genre')
        plt.ylabel('Number of Movies')
        plt.title('Number of Movies by Genre')
        plt.xticks(rotation=45)  # Rotate x-axis labels for better readability
        plt.tight_layout()

        # Define the path for saving the bar chart image file
        bar_chart_file_path = os.path.join(os.path.dirname(__file__), f'{request.user.username}_genre_distribution_bar_chart.png')

        # Save the bar chart as an image file
        plt.savefig(bar_chart_file_path)

        # Close the plot to release memory
        plt.close()

        # Generate a word cloud based on movie titles
        text = ' '.join(recommended_movies_df['Title'])
        wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)

        # Plot the word cloud
        plt.figure(figsize=(10, 6))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.title('Word Cloud of Movie Titles')
        plt.axis('off')  # Turn off axis
        plt.tight_layout()

        # Define the path for saving the word cloud image file
        wordcloud_file_path = os.path.join(os.path.dirname(__file__), f'{request.user.username}_wordcloud.png')

        # Save the word cloud as an image file
        plt.savefig(wordcloud_file_path)

        # Close the plot to release memory
        plt.close()

        print(f"Accuracy: {accuracy * 100:.2f}%")

        # Pagination
        paginator = Paginator(movie_list, 8)  # Show 8 movies per page

        page_number = request.GET.get('page')
        try:
            movie_list = paginator.page(page_number)
        except PageNotAnInteger:
            movie_list = paginator.page(1)
        except EmptyPage:
            movie_list = paginator.page(paginator.num_pages)

        context = {'movie_list': movie_list, 'accuracy': accuracy}
    else:
        # Handle the case when there is no data in the DataFrame
        context = {'movie_list': []}
        messages.warning(request, "No data available for recommendations. Please rate some movies to get personalized recommendations.")

    return render(request, 'recommend/recommend.html', context)




# Register user
def signUp(request):
    form = UserForm(request.POST or None)

    if form.is_valid():
        user = form.save(commit=False)
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user.set_password(password)
        user.save()
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")

    context = {'form': form}

    return render(request, 'recommend/signUp.html', context)


# Login User
def Login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")
            else:
                return render(request, 'recommend/login.html', {'error_message': 'Your account disable'})
        else:
            return render(request, 'recommend/login.html', {'error_message': 'Invalid Login'})

    return render(request, 'recommend/login.html')


# Logout user
def Logout(request):
    logout(request)
    return redirect("login")
